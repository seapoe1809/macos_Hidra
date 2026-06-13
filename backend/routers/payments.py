"""Recurring BTC payment endpoints (design: individual step 4)."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.services import payments

router = APIRouter(prefix="/api/payments", tags=["payments"])


class PaymentRequestBody(BaseModel):
    btc_address: str
    monthly_usd: float | None = None
    period: int = 1
    start_iso: str | None = None
    label: str | None = None


@router.get("/price")
def price():
    try:
        return {"btc_usd": payments.btc_usd_price()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Price feed error: {exc}")


@router.post("/request")
def make_request(req: PaymentRequestBody):
    try:
        return payments.payment_request(
            req.btc_address, req.monthly_usd, req.period, req.start_iso, req.label
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not build request: {exc}")
