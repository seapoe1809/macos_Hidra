"""Nostr encrypted-DM client (hub-and-spoke).

Consolidates the duplicated logic from app.py, sample_working_form.py and
sample_reading_message.py into one importable module. No Gradio, no globals:
relays and the hub npub come from config; the caller passes the nsec.
"""

import json
import ssl
import time
import binascii
from datetime import datetime

from bech32 import bech32_encode, convertbits
from nostr.filter import Filter, Filters
from nostr.event import EventKind, EncryptedDirectMessage
from nostr.relay_manager import RelayManager
from nostr.message_type import ClientMessageType
from nostr.key import PrivateKey, PublicKey

from backend import config


# --- key helpers -----------------------------------------------------------
def new_keypair() -> dict:
    """Generate a fresh Nostr keypair (the individual's encrypted ID)."""
    pk = PrivateKey()
    return {
        "nsec": pk.bech32(),
        "npub": pk.public_key.bech32(),
        "public_key_hex": pk.public_key.hex(),
        "private_key_hex": pk.hex(),
    }


def derive_npub(nsec: str) -> dict:
    """Derive public identifiers from an nsec."""
    pk = PrivateKey.from_nsec(nsec)
    return {
        "npub": pk.public_key.bech32(),
        "public_key_hex": pk.public_key.hex(),
        "private_key_hex": pk.hex(),
    }


def hex_to_npub(hex_key: str) -> str:
    data = binascii.unhexlify(hex_key)
    return bech32_encode("npub", convertbits(data, 8, 5))


def _recipient_hex(recipient: str) -> str:
    if recipient.startswith("npub"):
        return PublicKey.from_npub(recipient).hex()
    return recipient


def _open_kwargs() -> dict:
    return {"cert_reqs": ssl.CERT_NONE} if config.RELAY_INSECURE_SSL else {}


# --- sending ---------------------------------------------------------------
def send_dm(nsec: str, message: str, name: str | None = None, recipient: str | None = None) -> dict:
    """Encrypt and publish a DM to the hub (or an explicit recipient).

    Returns a dict with the event id and the keys used. Raises on failure.
    """
    recipient = recipient or config.HUB_NPUB
    formatted = f"Name:\U0001f464 {name}\n Message: ✎{message}" if name else message

    sender = PrivateKey.from_nsec(nsec)
    dm = EncryptedDirectMessage(
        recipient_pubkey=_recipient_hex(recipient),
        cleartext_content=formatted,
    )
    sender.sign_event(dm)

    rm = RelayManager()
    for relay in config.RELAYS:
        rm.add_relay(relay)
    rm.open_connections(_open_kwargs())
    try:
        time.sleep(1.0)
        rm.publish_event(dm)
        time.sleep(1.0)
    finally:
        rm.close_connections()

    return {
        "event_id": dm.id,
        "from_npub": sender.public_key.bech32(),
        "to": recipient if recipient.startswith("npub") else hex_to_npub(recipient),
    }


# --- reading ---------------------------------------------------------------
def read_dms(nsec: str, seconds: float | None = None) -> list[dict]:
    """Fetch & decrypt all DMs (sent and received) for the given nsec.

    Returns a flat, time-sorted list of message dicts:
        {id, peer_npub, created_at, formatted_time, content, is_sent}
    """
    if not nsec:
        raise ValueError("No NSEC key provided")
    seconds = config.DM_READ_SECONDS if seconds is None else seconds

    private_key = PrivateKey.from_nsec(nsec)
    pub_hex = private_key.public_key.hex()

    filters = Filters([
        Filter(kinds=[EventKind.ENCRYPTED_DIRECT_MESSAGE], pubkey_refs=[pub_hex]),
        Filter(kinds=[EventKind.ENCRYPTED_DIRECT_MESSAGE], authors=[pub_hex]),
    ])
    sub_id = "dm_subscription_" + str(int(time.time()))
    request = [ClientMessageType.REQUEST, sub_id]
    request.extend(filters.to_json_array())

    rm = RelayManager()
    for relay in config.RELAYS:
        rm.add_relay(relay)
    rm.add_subscription(sub_id, filters)
    rm.open_connections(_open_kwargs())
    time.sleep(1.25)

    messages: list[dict] = []
    try:
        rm.publish_message(json.dumps(request))
        time.sleep(seconds)

        while rm.message_pool.has_events():
            event_msg = rm.message_pool.get_event()
            ev = event_msg.event
            if ev.kind != EventKind.ENCRYPTED_DIRECT_MESSAGE:
                continue
            try:
                is_sent = ev.public_key == pub_hex
                if is_sent:
                    peer = next((t[1] for t in ev.tags if t[0] == "p"), None)
                    if peer is None:
                        continue
                else:
                    peer = ev.public_key

                decrypted = private_key.decrypt_message(
                    ev.content, peer if is_sent else ev.public_key
                )
                messages.append({
                    "id": ev.id,
                    "peer_npub": hex_to_npub(peer),
                    "created_at": ev.created_at,
                    "formatted_time": datetime.fromtimestamp(ev.created_at).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "content": decrypted,
                    "is_sent": is_sent,
                })
            except Exception as exc:  # noqa: BLE001 - skip undecryptable events
                print(f"Error processing DM: {exc}")
    finally:
        rm.close_connections()

    messages.sort(key=lambda m: m["created_at"])
    return messages


def conversations(nsec: str, seconds: float | None = None) -> dict[str, list[dict]]:
    """Group read_dms output by peer npub (for the hub mailbox view)."""
    grouped: dict[str, list[dict]] = {}
    for msg in read_dms(nsec, seconds):
        grouped.setdefault(msg["peer_npub"], []).append(msg)
    return grouped
