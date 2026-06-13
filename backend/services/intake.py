"""Parse the intake message string the hub receives into structured fields.

The individual messenger sends a body shaped like (from enroll.py / the original
form), optionally wrapped by the nostr client's "Name:.. Message:.." prefix:

    Name:👤 John Smith
     Message: ✎message = {name: Smith John, phone: 5551234567, DOB: 01/01/1980,
                          Place of Birth: Surrey, btc: bc1q...}

Design hospital step 6: a button that takes the string in a message, parses it,
and saves it to a SQL db. This module does the parsing half.
"""

import re

_FIELD_RE = re.compile(r"(\w[\w ]*?)\s*:\s*([^,}]+)")


def parse_intake(message_text: str) -> dict:
    """Extract key/value fields from an intake message. Returns a flat dict.

    Tolerant of the optional "Name:/Message:" wrapper and the ✎/👤 markers.
    The inner ``{...}`` block, if present, is what gets parsed for fields.
    """
    text = message_text or ""

    # Prefer the content inside the { ... } block if present.
    brace = re.search(r"\{(.+)\}", text, re.DOTALL)
    body = brace.group(1) if brace else text

    fields = {}
    for key, value in _FIELD_RE.findall(body):
        key = key.strip().lower().replace(" ", "_")
        value = value.strip().strip("✎👤 ")
        # ignore the literal "message =" leftover and empty values
        if key in ("message", "name_message") or not value:
            continue
        fields[key] = value

    return fields
