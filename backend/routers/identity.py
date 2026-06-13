"""Membership identity endpoints (dashboard box 2)."""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services import identity
from backend import db

router = APIRouter(prefix="/api/identity", tags=["identity"])


class GenerateRequest(BaseModel):
    year_of_birth: str
    last_name: str
    city_of_birth: str


class CheckRequest(BaseModel):
    # Provide ANY TWO of these — membership is proven without revealing the data.
    npub: str | None = None
    year_of_birth: str | None = None
    last_name: str | None = None
    place_of_birth: str | None = None
    city_of_birth: str | None = None  # backward-compat alias for place_of_birth


@router.post("/generate")
def generate(req: GenerateRequest):
    return identity.generate_ids(req.year_of_birth, req.last_name, req.city_of_birth)


@router.post("/check")
def check(req: CheckRequest):
    """Global 2-of-4 membership check. Hashes each supplied pair and looks it up
    in the pre-stored member_hashes index — no member id needed up front."""
    values = {
        "npub": req.npub,
        "year_of_birth": req.year_of_birth,
        "last_name": req.last_name,
        "place_of_birth": req.place_of_birth or req.city_of_birth,
    }
    present = {k: v for k, v in values.items() if v}
    if len(present) < 2:
        return {
            "success": False,
            "matches": [],
            "error": "Provide at least 2 of: npub, year of birth, place of birth, last name",
        }

    hashes = identity.identity_hashes(values)
    match = db.match_member_by_hashes(list(hashes.values()))
    if match:
        return {
            "success": True,
            "matches": [match["combo"]],
            "matched_npub": match["npub"],
        }
    return {"success": False, "matches": [], "error": "No match — not a member"}
