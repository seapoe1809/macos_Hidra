"""Parse a self-enrollment DM into structured member fields.

As the hub mailbox loads, individuals send a message shaped like:

    Name:👤 john smith Message: ✎message = {name: smith john, phone: 8038889021,
        DOB: 01/01/1985, Place of Birth: hartford, ct,
        btc: akjsdhafiulwkesrfbngwsrefnv}

We pull the ``{...}`` block and read the known keys. Unlike the simpler
``intake.parse_intake`` (which splits on every comma), this captures each value
up to the *next known key*, so commas inside a value survive — e.g.
"Place of Birth: hartford, ct" stays intact.

A message is only accepted as a member record when ALL five expected keys are
present ("said format"); anything else returns ``None`` and is ignored.
"""

import re

# Canonical field -> the aliases we accept for its key label.
_KEY_ALIASES = {
    "name": ["name"],
    "phone": ["phone", "cell phone", "cell", "phone/email"],
    "dob": ["dob", "date of birth"],
    "place_of_birth": ["place of birth", "place_of_birth", "city of birth", "birth place"],
    "btc": ["btc address", "btc", "wallet"],
}

# Alternation of every alias — used as a lookahead so one value stops where the
# next key begins, regardless of commas within the value itself.
_ALL_ALIASES = [a for aliases in _KEY_ALIASES.values() for a in aliases]
_NEXT_KEY = r"(?:" + "|".join(re.escape(a) for a in _ALL_ALIASES) + r")"


def _grab(body: str, aliases: list[str]) -> str | None:
    for alias in aliases:
        pat = (
            rf"{re.escape(alias)}\s*[:=]\s*"
            rf"(.*?)\s*(?=(?:[,;]\s*{_NEXT_KEY}\s*[:=])|$)"
        )
        m = re.search(pat, body, re.IGNORECASE | re.DOTALL)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def parse_member_message(content: str | None) -> dict | None:
    """Return {name, phone, dob, year_of_birth, place_of_birth, btc} or None.

    ``name`` is stored verbatim as "lastname firstname" (the order supplied in
    the message). ``year_of_birth`` is derived from the 4-digit year in DOB.
    Returns None when the message is not in the expected enrollment format.
    """
    if not content:
        return None
    block = re.search(r"\{(.+)\}", content, re.DOTALL)
    if not block:
        return None
    body = block.group(1)

    fields = {key: _grab(body, aliases) for key, aliases in _KEY_ALIASES.items()}
    # "said format" = all five keys found; otherwise ignore the message.
    if not all(fields.values()):
        return None

    year = None
    ym = re.search(r"\b(?:19|20)\d{2}\b", fields["dob"])
    if ym:
        year = ym.group(0)

    return {
        "name": fields["name"],            # "lastname firstname" as supplied
        "phone": fields["phone"],
        "dob": fields["dob"],
        "year_of_birth": year,
        "place_of_birth": fields["place_of_birth"],
        "btc": fields["btc"],
    }
