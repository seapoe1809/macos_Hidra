"""Blockchain audit — BTC payment ledger for the provider dashboard (box 3).

Refactored from audit.py to return plain dicts. Uses the public Blockstream API
(no key required). Given a member's BTC address it reports balance, totals, tx
count, and a payment-period summary aligned to the $20/mo plan.
"""

import requests

from backend import config

_BTC_BASE = "https://blockstream.info/api"


def audit_btc(address: str, show_transactions: bool = True, limit: int = 25) -> dict:
    """Audit a Bitcoin address. Returns a dict (never raises)."""
    try:
        addr = requests.get(f"{_BTC_BASE}/address/{address}", timeout=10)
        addr.raise_for_status()
        data = addr.json()

        chain = data.get("chain_stats", {})
        mem = data.get("mempool_stats", {})
        funded = chain.get("funded_txo_sum", 0)
        spent = chain.get("spent_txo_sum", 0)
        confirmed = funded - spent
        unconfirmed = mem.get("funded_txo_sum", 0) - mem.get("spent_txo_sum", 0)
        balance_sats = confirmed + unconfirmed
        tx_count = chain.get("tx_count", 0)

        transactions = []
        if show_transactions and tx_count > 0:
            txs = requests.get(f"{_BTC_BASE}/address/{address}/txs", timeout=10)
            txs.raise_for_status()
            tip = None
            for tx in txs.json()[:limit]:
                in_val = sum(
                    v.get("prevout", {}).get("value", 0)
                    for v in tx.get("vin", [])
                    if v.get("prevout", {}).get("scriptpubkey_address") == address
                )
                out_val = sum(
                    v.get("value", 0)
                    for v in tx.get("vout", [])
                    if v.get("scriptpubkey_address") == address
                )
                net = out_val - in_val
                status = tx.get("status", {})
                confs = 0
                if status.get("confirmed"):
                    if tip is None:
                        h = requests.get(f"{_BTC_BASE}/blocks/tip/height", timeout=5)
                        tip = int(h.text) if h.ok else status.get("block_height", 0)
                    confs = tip - status.get("block_height", tip) + 1
                transactions.append({
                    "txid": tx["txid"],
                    "amount_btc": abs(net) / 1e8,
                    "direction": "incoming" if net > 0 else "outgoing",
                    "confirmations": confs,
                    "block_time": status.get("block_time"),
                })

        incoming = [t for t in transactions if t["direction"] == "incoming"]
        last_payment = max((t["block_time"] for t in incoming if t["block_time"]), default=None)

        return {
            "success": True,
            "address": address,
            "balance_btc": balance_sats / 1e8,
            "balance_satoshis": balance_sats,
            "total_received_btc": funded / 1e8,
            "total_sent_btc": spent / 1e8,
            "tx_count": tx_count,
            # payment-ledger summary for the dashboard
            "periods_paid": len(incoming),
            "last_payment_unix": last_payment,
            "cumulative_received_btc": funded / 1e8,
            "transactions": transactions,
        }
    except requests.exceptions.RequestException as exc:
        return {"success": False, "address": address, "error": f"API request failed: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "address": address, "error": f"Audit failed: {exc}"}


def _net_for_address(tx: dict, address: str) -> int:
    """Signed satoshi delta this tx applies to `address` (received - sent)."""
    in_val = sum(
        v.get("prevout", {}).get("value", 0)
        for v in tx.get("vin", [])
        if v.get("prevout", {}).get("scriptpubkey_address") == address
    )
    out_val = sum(
        v.get("value", 0)
        for v in tx.get("vout", [])
        if v.get("scriptpubkey_address") == address
    )
    return out_val - in_val


def fetch_transactions(address: str, count: int = 20,
                       before_txid: str | None = None) -> dict:
    """Pull up to `count` transactions for an address, newest first.

    Blockstream returns ~25 per page; we chain pages via the last seen txid
    (`/txs/chain/{txid}`) until `count` is collected or the chain ends.
    `before_txid` resumes after a previous page (the "pull next" button passes
    the prior response's `last_txid`). Each tx is normalized to
    {txid, amount_btc, direction, block_time}.
    """
    try:
        collected: list[dict] = []
        last_seen = before_txid
        while len(collected) < count:
            if last_seen:
                url = f"{_BTC_BASE}/address/{address}/txs/chain/{last_seen}"
            else:
                url = f"{_BTC_BASE}/address/{address}/txs"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            page = r.json()
            if not page:
                break
            for tx in page:
                net = _net_for_address(tx, address)
                status = tx.get("status", {})
                collected.append({
                    "txid": tx["txid"],
                    "amount_btc": abs(net) / 1e8,
                    "direction": "incoming" if net > 0 else "outgoing",
                    "block_time": status.get("block_time"),
                })
                last_seen = tx["txid"]
                if len(collected) >= count:
                    break
            if len(page) < 25:  # short page = no more history
                break
        return {
            "success": True,
            "address": address,
            "transactions": collected,
            "last_txid": collected[-1]["txid"] if collected else before_txid,
            # heuristic: a full pull likely has more pages behind it
            "has_more": len(collected) >= count,
        }
    except requests.exceptions.RequestException as exc:
        return {"success": False, "address": address, "error": f"API request failed: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "address": address, "error": f"Fetch failed: {exc}"}
