"""PostgreSQL persistence for Darnahi · Project Hidra app data.

Stores the structured records the design needs that aren't on-chain or on
relays: hospital providers, their plans/services, enrolled members, and bills.

Backed by PostgreSQL via psycopg (v3). The connection target is driven by
``config.DATABASE_URL``. JSON payloads (services, id_hashes, intake fields) are
kept as TEXT json strings so every caller keeps the exact behaviour it had under
the previous sqlite layer (e.g. the frontend still JSON.parse's provider.services).
"""

import hashlib
import json
import time

import psycopg
from psycopg.rows import dict_row

from backend import config
from backend.services import identity

# DDL kept as discrete statements — psycopg's extended protocol runs one
# statement per execute(), so we loop rather than executescript().
SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS providers (
        id            SERIAL PRIMARY KEY,
        name          TEXT NOT NULL,
        npub          TEXT,
        btc_address   TEXT,
        services      TEXT,              -- JSON list: inpatient, clinic, telemed, ...
        created_at    BIGINT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS plans (
        id            SERIAL PRIMARY KEY,
        provider_id   INTEGER NOT NULL REFERENCES providers(id),
        monthly_usd   DOUBLE PRECISION NOT NULL,
        markup_pct    DOUBLE PRECISION NOT NULL,   -- cogs + markup_pct
        created_at    BIGINT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS members (
        id            SERIAL PRIMARY KEY,
        provider_id   INTEGER REFERENCES providers(id),
        npub          TEXT,              -- messenger id / encrypted identity
        btc_address   TEXT,
        id_hashes     TEXT,              -- JSON {combination: sha256}
        name          TEXT,              -- "lastname firstname" parsed from intake DM
        phone         TEXT,
        dob           TEXT,
        year_of_birth TEXT,
        place_of_birth TEXT,
        enrolled_at   BIGINT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS intakes (
        id            SERIAL PRIMARY KEY,
        provider_id   INTEGER REFERENCES providers(id),
        peer_npub     TEXT,              -- the individual's messenger id
        fields        TEXT,              -- JSON of parsed intake fields
        raw           TEXT,
        created_at    BIGINT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bills (
        id            SERIAL PRIMARY KEY,
        provider_id   INTEGER REFERENCES providers(id),
        member_npub   TEXT,              -- bills are keyed by messenger id (design box 4)
        description   TEXT,
        cogs_usd      DOUBLE PRECISION,
        total_usd     DOUBLE PRECISION,
        status        TEXT DEFAULT 'open',
        created_at    BIGINT NOT NULL
    )
    """,
    # messenger: every decrypted DM is persisted here as it loads, keyed by the
    # mailbox owner's npub and the peer npub. msg_id (nostr event id) makes each
    # row idempotent so repeated refreshes don't duplicate.
    """
    CREATE TABLE IF NOT EXISTS messenger (
        id            SERIAL PRIMARY KEY,
        owner_npub    TEXT NOT NULL,     -- whose mailbox this message belongs to
        peer_npub     TEXT,             -- the other party
        msg_id        TEXT NOT NULL,    -- nostr event id
        content       TEXT,
        is_sent       BOOLEAN,
        created_at    BIGINT,
        saved_at      BIGINT NOT NULL,
        UNIQUE (owner_npub, msg_id)
    )
    """,
    # member_hashes: pre-computed 2-of-4 identity hashes so the dashboard ID
    # check is a single indexed lookup instead of scanning members. One row per
    # (member, combo); many members may share a hash value (data collision),
    # so the dedup key is (member_id, combo), and `hash` is the search index.
    """
    CREATE TABLE IF NOT EXISTS member_hashes (
        id          SERIAL PRIMARY KEY,
        member_id   INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
        npub        TEXT,
        combo       TEXT NOT NULL,     -- e.g. last_name__year_of_birth
        hash        TEXT NOT NULL,
        UNIQUE (member_id, combo)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_member_hashes_hash ON member_hashes (hash)",
    # btc_audits: on-chain transactions pulled for an address (dashboard box 3),
    # persisted so they're searchable. npub is linked when the address belongs
    # to a known member. Idempotent per (btc_address, txid).
    """
    CREATE TABLE IF NOT EXISTS btc_audits (
        id           SERIAL PRIMARY KEY,
        btc_address  TEXT NOT NULL,
        txid         TEXT NOT NULL,
        amount_btc   DOUBLE PRECISION,
        direction    TEXT,              -- incoming / outgoing
        block_time   BIGINT,            -- transaction date (unix)
        npub         TEXT,              -- linked member npub, if the address matches
        saved_at     BIGINT NOT NULL,
        UNIQUE (btc_address, txid)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_btc_audits_npub ON btc_audits (npub)",
    "CREATE INDEX IF NOT EXISTS idx_btc_audits_addr ON btc_audits (btc_address)",
]


# Idempotent column adds for DBs created before the members table grew the
# parsed-intake fields. Safe to run on every startup.
MIGRATIONS = [
    # providers: street address + per-provider dashboard login token.
    "ALTER TABLE providers ADD COLUMN IF NOT EXISTS address TEXT",
    "ALTER TABLE providers ADD COLUMN IF NOT EXISTS login_token TEXT",
    "ALTER TABLE members ADD COLUMN IF NOT EXISTS name TEXT",
    "ALTER TABLE members ADD COLUMN IF NOT EXISTS phone TEXT",
    "ALTER TABLE members ADD COLUMN IF NOT EXISTS dob TEXT",
    "ALTER TABLE members ADD COLUMN IF NOT EXISTS year_of_birth TEXT",
    "ALTER TABLE members ADD COLUMN IF NOT EXISTS place_of_birth TEXT",
    # bills: new bill screen fields (amount, date, paid status, attachment).
    "ALTER TABLE bills ADD COLUMN IF NOT EXISTS amount_usd DOUBLE PRECISION",
    "ALTER TABLE bills ADD COLUMN IF NOT EXISTS bill_date TEXT",
    "ALTER TABLE bills ADD COLUMN IF NOT EXISTS paid BOOLEAN DEFAULT FALSE",
    "ALTER TABLE bills ADD COLUMN IF NOT EXISTS paid_at BIGINT",
    "ALTER TABLE bills ADD COLUMN IF NOT EXISTS attachment_path TEXT",
    "ALTER TABLE bills ADD COLUMN IF NOT EXISTS attachment_name TEXT",
    "ALTER TABLE bills ADD COLUMN IF NOT EXISTS attachment_type TEXT",
]


def connect():
    """Open a new connection with dict rows. Caller uses it as a context manager."""
    return psycopg.connect(config.DATABASE_URL, row_factory=dict_row)


def init_db():
    with connect() as conn:
        with conn.cursor() as cur:
            for stmt in SCHEMA:
                cur.execute(stmt)
            for stmt in MIGRATIONS:
                cur.execute(stmt)
        conn.commit()
    # Index any pre-existing parsed members for the fast ID check.
    backfill_member_hashes()


def _now() -> int:
    return int(time.time())


# --- providers / plans -----------------------------------------------------
def create_provider(name: str, npub: str, btc_address: str, services: list[str],
                    address: str | None = None, login_token: str | None = None) -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO providers (name, npub, btc_address, services, address, login_token, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (name, npub, btc_address, json.dumps(services or []), address, login_token, _now()),
            )
            new_id = cur.fetchone()["id"]
        conn.commit()
        return new_id


def hash_token(token: str) -> str:
    """SHA-256 of a login token. Providers' tokens (npub or generated nsec) are
    stored only as this hash, never in plaintext."""
    return hashlib.sha256((token or "").encode()).hexdigest()


def find_provider_by_token(token: str) -> dict | None:
    """Return the provider whose dashboard login token matches, or None.
    The raw token is hashed before the lookup."""
    if not token:
        return None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM providers WHERE login_token=%s LIMIT 1",
                (hash_token(token),),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def create_plan(provider_id: int, monthly_usd: float, markup_pct: float) -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO plans (provider_id, monthly_usd, markup_pct, created_at) "
                "VALUES (%s,%s,%s,%s) RETURNING id",
                (provider_id, monthly_usd, markup_pct, _now()),
            )
            new_id = cur.fetchone()["id"]
        conn.commit()
        return new_id


def get_provider(provider_id: int) -> dict | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM providers WHERE id=%s", (provider_id,))
            row = cur.fetchone()
        return dict(row) if row else None


# --- members ---------------------------------------------------------------
def create_member(provider_id: int, npub: str, btc_address: str, id_hashes: dict) -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO members (provider_id, npub, btc_address, id_hashes, enrolled_at) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (provider_id, npub, btc_address, json.dumps(id_hashes or {}), _now()),
            )
            new_id = cur.fetchone()["id"]
        conn.commit()
        return new_id


def _last_name(name: str | None) -> str | None:
    """Members store name as "lastname firstname"; the last name is the first token."""
    return name.split()[0] if name and name.split() else None


def index_member_hashes(member_id: int, npub: str | None, fields: dict) -> int:
    """Pre-compute & store this member's 2-of-4 identity hashes for fast lookup.

    `fields` may carry year_of_birth, last_name, place_of_birth; npub is added in.
    Idempotent per (member_id, combo). Returns the number of combos stored.
    """
    values = {**fields, "npub": npub}
    hashes = identity.identity_hashes(values)
    if not hashes:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            for combo, h in hashes.items():
                cur.execute(
                    "INSERT INTO member_hashes (member_id, npub, combo, hash) "
                    "VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (member_id, combo) DO UPDATE SET hash=EXCLUDED.hash",
                    (member_id, npub, combo, h),
                )
        conn.commit()
    return len(hashes)


def match_member_by_hashes(hashes: list[str]) -> dict | None:
    """Return the first member matching any of these identity-pair hashes, or None.

    Single indexed lookup over member_hashes (idx_member_hashes_hash).
    """
    if not hashes:
        return None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT mh.member_id, mh.npub, mh.combo, m.name "
                "FROM member_hashes mh JOIN members m ON m.id = mh.member_id "
                "WHERE mh.hash = ANY(%s) LIMIT 1",
                (hashes,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def backfill_member_hashes() -> int:
    """Index any parsed members that don't yet have hashes (e.g. created before
    this feature). Idempotent. Returns the number of members (re)indexed."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, npub, name, year_of_birth, place_of_birth "
                "FROM members WHERE name IS NOT NULL"
            )
            rows = cur.fetchall()
    for r in rows:
        index_member_hashes(r["id"], r["npub"], {
            "year_of_birth": r["year_of_birth"],
            "last_name": _last_name(r["name"]),
            "place_of_birth": r["place_of_birth"],
        })
    return len(rows)


def save_parsed_member(npub: str, parsed: dict) -> bool:
    """Store an intake-parsed member (from a DM) keyed by npub. Dedup: if a
    member with this npub already carries a parsed name, ignore. Returns True if
    a new row was inserted, False if it was a duplicate or had no npub.

    On insert, the member's 2-of-4 identity hashes are pre-stored for fast
    dashboard ID checks.
    """
    if not npub:
        return False
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM members WHERE npub=%s AND name IS NOT NULL",
                (npub,),
            )
            if cur.fetchone():
                return False  # duplicate — ignore
            cur.execute(
                "INSERT INTO members "
                "(npub, name, phone, dob, year_of_birth, place_of_birth, btc_address, enrolled_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (
                    npub,
                    parsed.get("name"),
                    parsed.get("phone"),
                    parsed.get("dob"),
                    parsed.get("year_of_birth"),
                    parsed.get("place_of_birth"),
                    parsed.get("btc"),
                    _now(),
                ),
            )
            member_id = cur.fetchone()["id"]
        conn.commit()
    index_member_hashes(member_id, npub, {
        "year_of_birth": parsed.get("year_of_birth"),
        "last_name": _last_name(parsed.get("name")),
        "place_of_birth": parsed.get("place_of_birth"),
    })
    return True


def find_member_id_hashes(npub: str) -> dict | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_hashes FROM members WHERE npub=%s", (npub,))
            row = cur.fetchone()
        return json.loads(row["id_hashes"]) if row else None


# --- intakes ---------------------------------------------------------------
def create_intake(provider_id: int, peer_npub: str, fields: dict, raw: str) -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO intakes (provider_id, peer_npub, fields, raw, created_at) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (provider_id, peer_npub, json.dumps(fields or {}), raw, _now()),
            )
            new_id = cur.fetchone()["id"]
        conn.commit()
        return new_id


def list_intakes(provider_id: int | None = None) -> list[dict]:
    with connect() as conn:
        with conn.cursor() as cur:
            if provider_id:
                cur.execute(
                    "SELECT * FROM intakes WHERE provider_id=%s ORDER BY created_at DESC",
                    (provider_id,),
                )
            else:
                cur.execute("SELECT * FROM intakes ORDER BY created_at DESC")
            return [dict(r) for r in cur.fetchall()]


# --- bills -----------------------------------------------------------------
def create_bill(provider_id: int, member_npub: str, description: str,
                cogs_usd: float, markup_pct: float) -> dict:
    total = round(cogs_usd * (1 + markup_pct / 100.0), 2)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO bills (provider_id, member_npub, description, cogs_usd, total_usd, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (provider_id, member_npub, description, cogs_usd, total, _now()),
            )
            bill_id = cur.fetchone()["id"]
        conn.commit()
    return {"id": bill_id, "total_usd": total, "cogs_usd": cogs_usd}


def list_bills(member_npub: str | None = None) -> list[dict]:
    with connect() as conn:
        with conn.cursor() as cur:
            if member_npub:
                cur.execute(
                    "SELECT * FROM bills WHERE member_npub=%s ORDER BY created_at DESC",
                    (member_npub,),
                )
            else:
                cur.execute("SELECT * FROM bills ORDER BY created_at DESC")
            return [dict(r) for r in cur.fetchall()]


# --- bills (standalone bill screen) ----------------------------------------
def add_bill_record(member_npub: str, amount_usd: float, bill_date: str,
                    attachment: dict | None = None) -> dict:
    """Insert a bill (npub, amount, date, optional PDF/photo). Unpaid by default."""
    att = attachment or {}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO bills "
                "(member_npub, amount_usd, bill_date, paid, "
                " attachment_path, attachment_name, attachment_type, created_at) "
                "VALUES (%s,%s,%s,FALSE,%s,%s,%s,%s) RETURNING id",
                (
                    member_npub, amount_usd, bill_date,
                    att.get("path"), att.get("name"), att.get("type"), _now(),
                ),
            )
            bill_id = cur.fetchone()["id"]
        conn.commit()
    return get_bill(bill_id)


def get_bill(bill_id: int) -> dict | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bills WHERE id=%s", (bill_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def search_bills(npub: str | None = None) -> list[dict]:
    """Bills filtered by member npub (partial, case-insensitive), or all."""
    with connect() as conn:
        with conn.cursor() as cur:
            if npub:
                cur.execute(
                    "SELECT * FROM bills WHERE member_npub ILIKE %s ORDER BY created_at DESC",
                    (f"%{npub.strip()}%",),
                )
            else:
                cur.execute("SELECT * FROM bills ORDER BY created_at DESC")
            return [dict(r) for r in cur.fetchall()]


def mark_bill_paid(bill_id: int) -> dict | None:
    """Mark a bill paid, stamping the moment the button was clicked."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bills SET paid=TRUE, paid_at=%s, status='paid' "
                "WHERE id=%s RETURNING id",
                (_now(), bill_id),
            )
            row = cur.fetchone()
        conn.commit()
    return get_bill(bill_id) if row else None


# --- messenger -------------------------------------------------------------
def save_messages(owner_npub: str, messages: list[dict]) -> int:
    """Persist decrypted DMs as they load. Idempotent per (owner_npub, msg_id).

    Each message dict follows nostr_client.read_dms output:
        {id, peer_npub, created_at, content, is_sent}
    Returns the number of newly-inserted rows.
    """
    if not owner_npub or not messages:
        return 0
    saved_at = _now()
    inserted = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for m in messages:
                cur.execute(
                    "INSERT INTO messenger "
                    "(owner_npub, peer_npub, msg_id, content, is_sent, created_at, saved_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (owner_npub, msg_id) DO NOTHING",
                    (
                        owner_npub, m.get("peer_npub"), m.get("id"),
                        m.get("content"), m.get("is_sent"),
                        m.get("created_at"), saved_at,
                    ),
                )
                inserted += cur.rowcount
        conn.commit()
    return inserted


def list_messenger(owner_npub: str) -> dict[str, list[dict]]:
    """Return persisted messages for an owner, grouped by peer npub (chronological)."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT peer_npub, msg_id, content, is_sent, created_at "
                "FROM messenger WHERE owner_npub=%s ORDER BY created_at ASC",
                (owner_npub,),
            )
            grouped: dict[str, list[dict]] = {}
            for r in cur.fetchall():
                grouped.setdefault(r["peer_npub"], []).append(dict(r))
            return grouped


# --- btc audits ------------------------------------------------------------
def find_member_npub_by_btc(address: str) -> str | None:
    """Return the npub of a member whose BTC address matches, or None."""
    if not address:
        return None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT npub FROM members WHERE btc_address=%s AND npub IS NOT NULL LIMIT 1",
                (address,),
            )
            row = cur.fetchone()
            return row["npub"] if row else None


def save_btc_audits(address: str, npub: str | None, transactions: list[dict]) -> int:
    """Persist pulled transactions. Idempotent per (btc_address, txid). If the
    member link (npub) becomes known later, it backfills on conflict. Returns
    the number of rows written/updated."""
    if not address or not transactions:
        return 0
    saved_at = _now()
    written = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for t in transactions:
                cur.execute(
                    "INSERT INTO btc_audits "
                    "(btc_address, txid, amount_btc, direction, block_time, npub, saved_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (btc_address, txid) DO UPDATE "
                    "SET npub = COALESCE(EXCLUDED.npub, btc_audits.npub)",
                    (
                        address, t.get("txid"), t.get("amount_btc"),
                        t.get("direction"), t.get("block_time"), npub, saved_at,
                    ),
                )
                written += cur.rowcount
        conn.commit()
    return written


def search_btc_audits(q: str, limit: int = 200) -> list[dict]:
    """Search persisted audits by npub OR btc address (partial, case-insensitive)."""
    if not q:
        return []
    like = f"%{q.strip()}%"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT btc_address, txid, amount_btc, direction, block_time, npub "
                "FROM btc_audits WHERE npub ILIKE %s OR btc_address ILIKE %s "
                "ORDER BY block_time DESC NULLS LAST LIMIT %s",
                (like, like, limit),
            )
            return [dict(r) for r in cur.fetchall()]
