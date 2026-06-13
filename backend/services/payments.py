"""Recurring BTC payment helper (design: individual step 4).

Bitcoin has no native standing order, so the honest model is: each month we
produce a *payment request* — a BIP21 URI (bitcoin:<addr>?amount=<btc>) that any
wallet can pay — priced from the live BTC/USD rate. No private keys are held
server-side; the Member's own wallet signs and broadcasts.

`audit.py` proves on-chain that the payments arrived.
"""

from datetime import datetime, timezone, timedelta

import requests

from backend import config

_PRICE_URL = "https://api.coinbase.com/v2/prices/BTC-USD/spot"


def btc_usd_price() -> float:
    """Current BTC price in USD (Coinbase spot). Raises on failure."""
    r = requests.get(_PRICE_URL, timeout=10)
    r.raise_for_status()
    return float(r.json()["data"]["amount"])


def _next_due(start_iso: str | None, period: int) -> str:
    """Next monthly due date as ISO (approx 30-day periods from start/now)."""
    base = (
        datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc)
        if start_iso else datetime.now(timezone.utc)
    )
    return (base + timedelta(days=30 * period)).strftime("%Y-%m-%d")


def payment_request(
    btc_address: str,
    monthly_usd: float | None = None,
    period: int = 1,
    start_iso: str | None = None,
    label: str | None = None,
) -> dict:
    """Build a monthly BIP21 payment request priced at the live rate."""
    monthly_usd = config.PLAN_MONTHLY_USD if monthly_usd is None else monthly_usd
    price = btc_usd_price()
    amount_btc = round(monthly_usd / price, 8)

    params = [f"amount={amount_btc:.8f}"]
    if label:
        # naive URL-encode of spaces; labels are short hospital names
        params.append("label=" + label.replace(" ", "%20"))
    bip21 = f"bitcoin:{btc_address}?" + "&".join(params)

    return {
        "btc_address": btc_address,
        "monthly_usd": monthly_usd,
        "btc_usd_price": price,
        "amount_btc": amount_btc,
        "bip21_uri": bip21,
        "due_date": _next_due(start_iso, period),
        "period": period,
        "note": "No standing order on Bitcoin — pay this request from your own wallet each month.",
    }
