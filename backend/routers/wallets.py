"""Wallet generation endpoints."""

from fastapi import APIRouter, HTTPException

from backend.services import wallets

router = APIRouter(prefix="/api/wallets", tags=["wallets"])


@router.post("/btc")
def create_btc_wallet():
    return wallets.generate_btc_wallet()


@router.post("/xmr")
def create_xmr_wallet():
    try:
        return wallets.generate_xmr_wallet()
    except ImportError:
        raise HTTPException(status_code=501, detail="monero library not installed")
