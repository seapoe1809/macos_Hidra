"""Blockchain audit endpoints (provider dashboard box 3 + audit page)."""

from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.services import audit
from backend import db

router = APIRouter(prefix="/api/audit", tags=["audit"])


class PullRequest(BaseModel):
    address: str
    count: int = 20
    before_txid: str | None = None  # resume after a prior page ("pull next")


@router.get("/btc/{address}")
def audit_btc(address: str, transactions: bool = Query(True)):
    return audit.audit_btc(address, show_transactions=transactions)


@router.post("/pull")
def pull(req: PullRequest):
    """Fetch a page of on-chain transactions, link a member npub if the address
    matches one, persist them to btc_audits, and return the page."""
    address = req.address.strip()
    res = audit.fetch_transactions(address, count=req.count, before_txid=req.before_txid)
    if not res.get("success"):
        return res
    npub = db.find_member_npub_by_btc(address)
    db.save_btc_audits(address, npub, res["transactions"])
    res["npub"] = npub
    for t in res["transactions"]:
        t["npub"] = npub
    return res


@router.get("/search")
def search(q: str = Query(..., min_length=1)):
    """Search persisted audits by npub or BTC address (partial match)."""
    return {"results": db.search_btc_audits(q)}
