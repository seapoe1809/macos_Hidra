"""Hospital provider endpoints (design: provider steps 1-4, dashboard box 4).

Registration + plan creation, token login, and bills-by-messenger-id. The
dashboard's other boxes are served by the messaging/identity/audit routers.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import config, db
from backend.services import intake as intake_svc, nostr_client

router = APIRouter(prefix="/api/provider", tags=["provider"])


class LoginRequest(BaseModel):
    token: str


class RegisterRequest(BaseModel):
    name: str
    address: str | None = None
    npub: str | None = None           # blank -> a keypair is generated server-side
    btc_address: str
    services: list[str] = []          # inpatient, clinic, telemed, medicines, er, labs, hospice, home_health, ...
    monthly_usd: float | None = None
    markup_pct: float | None = None


class IntakeRequest(BaseModel):
    provider_id: int | None = None
    peer_npub: str | None = None
    message_text: str


class BillRequest(BaseModel):
    provider_id: int
    member_npub: str
    description: str
    cogs_usd: float
    markup_pct: float | None = None


@router.post("/login")
def login(req: LoginRequest):
    # Accept the master token (config) OR any provider's own login token.
    if req.token == config.PROVIDER_TOKEN or db.find_provider_by_token(req.token):
        return {"success": True}
    raise HTTPException(status_code=401, detail="Incorrect token")


@router.post("/register")
def register(req: RegisterRequest):
    # npub is required; if blank, generate a keypair. The generated nsec is shown
    # once (the provider must save it) and becomes the dashboard login token.
    keys = None
    npub = (req.npub or "").strip()
    if npub:
        login_token = npub
    else:
        keys = nostr_client.new_keypair()
        npub = keys["npub"]
        login_token = keys["nsec"]

    provider_id = db.create_provider(
        req.name, npub, req.btc_address, req.services,
        address=req.address, login_token=db.hash_token(login_token),  # store only the hash
    )
    plan_id = db.create_plan(
        provider_id,
        req.monthly_usd if req.monthly_usd is not None else config.PLAN_MONTHLY_USD,
        req.markup_pct if req.markup_pct is not None else config.PLAN_MARKUP_PCT,
    )
    return {
        "success": True,
        "provider_id": provider_id,
        "plan_id": plan_id,
        "npub": npub,
        "login_token": login_token,        # what the dashboard logs in with
        "generated_keys": keys,            # present (nsec/npub) only if auto-generated
        "btc_address": req.btc_address,
        # shareable individual form — carries the hospital npub so a member's
        # intake is DM'd straight to this hospital's mailbox.
        "enroll_link": f"/user/?provider={provider_id}&hub={npub}",
    }


@router.get("/{provider_id}")
def get_provider(provider_id: int):
    provider = db.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


@router.post("/intake")
def save_intake(req: IntakeRequest):
    """Parse an intake message string and persist it (hospital step 6)."""
    fields = intake_svc.parse_intake(req.message_text)
    intake_id = db.create_intake(req.provider_id, req.peer_npub, fields, req.message_text)
    return {"success": True, "intake_id": intake_id, "fields": fields}


@router.get("/intake/list")
def list_intakes(provider_id: int | None = None):
    return {"intakes": db.list_intakes(provider_id)}


@router.post("/bills")
def create_bill(req: BillRequest):
    markup = req.markup_pct if req.markup_pct is not None else config.PLAN_MARKUP_PCT
    return db.create_bill(req.provider_id, req.member_npub, req.description, req.cogs_usd, markup)


@router.get("/bills/list")
def list_bills(member_npub: str | None = None):
    return {"bills": db.list_bills(member_npub)}
