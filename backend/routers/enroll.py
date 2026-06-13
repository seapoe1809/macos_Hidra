"""Individual enrollment (design steps 1-4).

Generates the encrypted identity (Nostr keypair = messenger key), derives the
membership ID hashes, persists the member, and sends the signed intake message
to the hospital hub.
"""

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services import nostr_client, identity
from backend import db

router = APIRouter(prefix="/api/enroll", tags=["enroll"])


class EnrollRequest(BaseModel):
    first_name: str
    last_name: str
    phone: str | None = None
    dob: str | None = None              # DD/MM/YYYY
    year_of_birth: str | None = None    # used for id hashes
    birth_place: str | None = None
    btc_address: str | None = None
    provider_id: int | None = None
    hub_npub: str | None = None         # hospital mailbox the intake is sent to
    agree: bool = False
    send_message: bool = True


@router.post("")
async def enroll(req: EnrollRequest):
    if not req.agree:
        return {"success": False, "error": "Enrollment requires consent"}

    # 1. Encrypted identity / messenger key
    keys = nostr_client.new_keypair()

    # 2. Membership ID hashes (2-of-3), if we have the fields
    id_hashes = {}
    yob = req.year_of_birth or (req.dob.split("/")[-1] if req.dob else None)
    if yob and req.last_name and req.birth_place:
        id_hashes = identity.generate_ids(yob, req.last_name, req.birth_place)

    # 3. Persist the member
    member_id = db.create_member(
        provider_id=req.provider_id,
        npub=keys["npub"],
        btc_address=req.btc_address,
        id_hashes=id_hashes,
    )

    # Pre-store the 2-of-4 identity hashes (npub, year, last name, place) so the
    # dashboard ID check finds this member with any two of them.
    db.index_member_hashes(member_id, keys["npub"], {
        "year_of_birth": yob,
        "last_name": req.last_name,
        "place_of_birth": req.birth_place,
    })

    # 4. Transmit signed intake to the hospital mailbox. Prefer the npub passed
    # from the form (carried by the enrollment link); else look it up from the
    # provider; else fall back to the configured default hub.
    send_result = None
    if req.send_message:
        intake = (
            f"message = {{name: {req.last_name} {req.first_name}, phone: {req.phone}, "
            f"DOB: {req.dob}, Place of Birth: {req.birth_place}, btc: {req.btc_address}}}"
        )
        full_name = f"{req.first_name} {req.last_name}"
        recipient = req.hub_npub
        if not recipient and req.provider_id:
            prov = db.get_provider(req.provider_id)
            recipient = prov.get("npub") if prov else None
        send_result = await asyncio.to_thread(
            nostr_client.send_dm, keys["nsec"], intake, full_name, recipient
        )

    return {
        "success": True,
        "member_id": member_id,
        "identity": keys,          # includes nsec — show once, user must save
        "id_hashes": id_hashes,
        "message_sent": send_result,
    }
