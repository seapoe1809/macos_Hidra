"""Nostr messaging endpoints + live mailbox WebSocket.

REST for send/read; WebSocket streams refreshed conversations to the hub
(provider dashboard box 1) and to individual messengers.
"""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend import db
from backend.services import member_parser, nostr_client

router = APIRouter(prefix="/api/messages", tags=["messaging"])


class SendRequest(BaseModel):
    nsec: str
    message: str
    name: str | None = None
    recipient: str | None = None  # defaults to hub npub


class ReadRequest(BaseModel):
    nsec: str
    seconds: float | None = None


@router.post("/send")
async def send(req: SendRequest):
    # nostr_client.send_dm is blocking (relay sockets) — run off the event loop.
    return await asyncio.to_thread(
        nostr_client.send_dm, req.nsec, req.message, req.name, req.recipient
    )


@router.post("/read")
async def read(req: ReadRequest):
    messages = await asyncio.to_thread(nostr_client.read_dms, req.nsec, req.seconds)
    return {"messages": messages}


@router.post("/conversations")
async def conversations(req: ReadRequest):
    convos = await asyncio.to_thread(nostr_client.conversations, req.nsec, req.seconds)
    return {"conversations": convos}


def _load_and_persist(nsec: str, seconds: float | None):
    """Read DMs, save each to the messenger table, parse any enrollment-format
    messages into the members table, return (npub, conversations, members_added)."""
    owner_npub = nostr_client.derive_npub(nsec)["npub"]
    messages = nostr_client.read_dms(nsec, seconds)
    db.save_messages(owner_npub, messages)

    # Any message in the "{name:.., phone:.., DOB:.., Place of Birth:.., btc:..}"
    # format becomes a member row keyed by the peer's npub. Off-format or
    # duplicate (same npub already stored) messages are silently ignored.
    members_added = 0
    for m in messages:
        parsed = member_parser.parse_member_message(m.get("content"))
        if parsed and db.save_parsed_member(m.get("peer_npub"), parsed):
            members_added += 1

    grouped: dict[str, list[dict]] = {}
    for m in messages:
        grouped.setdefault(m["peer_npub"], []).append(m)
    return owner_npub, grouped, members_added


@router.post("/load")
async def load(req: ReadRequest):
    """Messenger page: fetch conversations AND persist them to the DB as they load."""
    owner_npub, convos, members_added = await asyncio.to_thread(
        _load_and_persist, req.nsec, req.seconds
    )
    saved = sum(len(v) for v in convos.values())
    return {
        "npub": owner_npub,
        "conversations": convos,
        "message_count": saved,
        "members_added": members_added,
    }


@router.websocket("/ws")
async def mailbox_ws(websocket: WebSocket):
    """Client sends {"nsec": "...", "interval": 30}; server pushes conversations."""
    await websocket.accept()
    try:
        cfg = await websocket.receive_json()
        nsec = cfg.get("nsec")
        interval = float(cfg.get("interval", 30))
        if not nsec:
            await websocket.send_json({"error": "nsec required"})
            await websocket.close()
            return
        while True:
            convos = await asyncio.to_thread(nostr_client.conversations, nsec)
            await websocket.send_json({"conversations": convos})
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001
        try:
            await websocket.send_json({"error": str(exc)})
        finally:
            await websocket.close()
