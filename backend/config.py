"""Central configuration for the Hidra backend.

Everything that used to be hardcoded across app.py / sample_*_message.py
(relays, the hub npub, the provider login token, default keys) lives here and
is driven by environment variables so nothing secret needs to be committed.

A `.env` file at the project root is loaded automatically (without adding a
dependency) so `setup.py` can generate strong secrets that `darnahi` picks up.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def _load_dotenv(path: str) -> None:
    """Minimal .env loader: KEY=VALUE lines, no export/quotes parsing magic.
    Existing real environment variables always win over the file."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


_load_dotenv(os.path.join(_ROOT, ".env"))

# --- Nostr -----------------------------------------------------------------
# The hospital "hub" public key. Spokes (individuals) DM this npub.
HUB_NPUB = os.environ.get(
    "HIDRA_HUB_NPUB",
    "npub13sftpd43mhct2dyn8w2grlp0g40a4fsmp4z7ccx8gjmw87gex6csn5fjlx",
)

# Relays used for publishing and reading encrypted DMs.
RELAYS = os.environ.get(
    "HIDRA_RELAYS",
    ",".join(
        [
            "wss://relay.damus.io",
            "wss://relay.primal.net",
            "wss://nos.lol",
            "wss://relay.nostr.band",
            "wss://nostr-pub.wellorder.net",
        ]
    ),
).split(",")

# How long read_dms waits (seconds) for relays to return events.
DM_READ_SECONDS = float(os.environ.get("HIDRA_DM_READ_SECONDS", "3"))

# When True, relay TLS certs are NOT verified (matches the original prototype
# behaviour). Default False — opt back in only if a relay misbehaves.
RELAY_INSECURE_SSL = os.environ.get("HIDRA_RELAY_INSECURE_SSL", "false").lower() == "true"

# --- Provider auth ---------------------------------------------------------
# Master dashboard token. Each provider also gets its own login token (hashed
# in the DB). Set HIDRA_PROVIDER_TOKEN in the env / .env. The legacy default
# "token123" is insecure and only tolerated so dev still boots — a loud warning
# is printed below if it's left in place.
_INSECURE_DEFAULT_TOKEN = "token123"
PROVIDER_TOKEN = os.environ.get("HIDRA_PROVIDER_TOKEN", _INSECURE_DEFAULT_TOKEN)

# --- Plan / billing defaults ----------------------------------------------
PLAN_MONTHLY_USD = float(os.environ.get("HIDRA_PLAN_MONTHLY_USD", "20"))
PLAN_MARKUP_PCT = float(os.environ.get("HIDRA_PLAN_MARKUP_PCT", "10"))  # cogs + 10%

# --- Storage ---------------------------------------------------------------
# PostgreSQL connection string (psycopg / libpq DSN). Defaults to the local
# Docker instance provisioned by setup.py:
#   docker run -d --name hidra-pg -e POSTGRES_USER=hidra \
#       -e POSTGRES_PASSWORD=<generated> -e POSTGRES_DB=hidra \
#       -p 5433:5432 postgres:16
DATABASE_URL = os.environ.get(
    "HIDRA_DATABASE_URL",
    "postgresql://hidra:hidra_secret@127.0.0.1:5433/hidra",
)

# Where uploaded bill attachments (PDF / photo) are written.
UPLOAD_DIR = os.environ.get("HIDRA_UPLOAD_DIR", os.path.join(_ROOT, "bill_uploads"))

# Max accepted upload size for bill attachments (bytes). Default 10 MB.
MAX_UPLOAD_BYTES = int(os.environ.get("HIDRA_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))

# --- Frontend --------------------------------------------------------------
FRONTEND_DIR = os.environ.get("HIDRA_FRONTEND_DIR", os.path.join(_ROOT, "frontend"))

# CORS origins for the JS frontend (comma separated). The frontend is served
# from the same origin, so the safe default is "same-origin only" (no extra
# origins). Set HIDRA_CORS_ORIGINS="*" or a list only if calling cross-origin.
CORS_ORIGINS = [o for o in os.environ.get("HIDRA_CORS_ORIGINS", "").split(",") if o]


# --- Startup safety checks -------------------------------------------------
def is_insecure_default_token() -> bool:
    return PROVIDER_TOKEN == _INSECURE_DEFAULT_TOKEN


def warn_on_insecure_config() -> None:
    """Emit loud warnings for insecure settings. Called once at app startup."""
    if is_insecure_default_token():
        print(
            "\n  ⚠  HIDRA_PROVIDER_TOKEN is the insecure default 'token123'.\n"
            "     Set a strong token in .env before exposing this service.\n",
            file=sys.stderr,
        )
    if RELAY_INSECURE_SSL:
        print(
            "  ⚠  HIDRA_RELAY_INSECURE_SSL is on — relay TLS certs are NOT verified.\n",
            file=sys.stderr,
        )
