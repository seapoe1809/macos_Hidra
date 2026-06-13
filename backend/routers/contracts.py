"""Contract PDF endpoint (design: individual step 5 / provider step 3)."""

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from backend.services import contract

router = APIRouter(prefix="/api/contract", tags=["contract"])


class ContractRequest(BaseModel):
    hospital_name: str
    individual_name: str | None = None
    btc_address: str | None = None
    npub: str | None = None
    monthly_usd: float | None = None
    markup_pct: float | None = None
    services: list[str] | None = None


@router.post("")
def make_contract(req: ContractRequest):
    pdf = contract.build_contract(
        hospital_name=req.hospital_name,
        individual_name=req.individual_name,
        btc_address=req.btc_address,
        npub=req.npub,
        monthly_usd=req.monthly_usd,
        markup_pct=req.markup_pct,
        services=req.services,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="hidra_contract.pdf"'},
    )
