"""BTC / XMR wallet generation.

Refactored from btc_wallet_generator.py and xmr_wallet_generator.py to return
dicts instead of printing. The XMR path is optional — it only works if the
`monero` library is importable.
"""

import os
import hashlib

import ecdsa
import base58
from Crypto.Hash import RIPEMD160


# --- Bitcoin ---------------------------------------------------------------
def _private_key_to_wif(private_key: bytes, compressed: bool = True) -> str:
    versioned = b"\x80" + private_key + (b"\x01" if compressed else b"")
    checksum = hashlib.sha256(hashlib.sha256(versioned).digest()).digest()[:4]
    return base58.b58encode(versioned + checksum).decode()


def _private_key_to_public_key(private_key: bytes, compressed: bool = True) -> bytes:
    sk = ecdsa.SigningKey.from_string(private_key, curve=ecdsa.SECP256k1)
    vk = sk.get_verifying_key()
    x, y = vk.to_string()[:32], vk.to_string()[32:]
    if compressed:
        return (b"\x02" if y[-1] % 2 == 0 else b"\x03") + x
    return b"\x04" + vk.to_string()


def _hash160(data: bytes) -> bytes:
    r = RIPEMD160.new()
    r.update(hashlib.sha256(data).digest())
    return r.digest()


def _public_key_to_address(public_key: bytes) -> str:
    versioned = b"\x00" + _hash160(public_key)
    checksum = hashlib.sha256(hashlib.sha256(versioned).digest()).digest()[:4]
    return base58.b58encode(versioned + checksum).decode()


def generate_btc_wallet() -> dict:
    """Generate a P2PKH (legacy) Bitcoin wallet."""
    private_key = os.urandom(32)
    public_key = _private_key_to_public_key(private_key, compressed=True)
    return {
        "currency": "BTC",
        "private_key_hex": private_key.hex(),
        "private_key_wif": _private_key_to_wif(private_key),
        "public_key_hex": public_key.hex(),
        "address": _public_key_to_address(public_key),
    }


# --- Monero ----------------------------------------------------------------
def generate_xmr_wallet() -> dict:
    """Generate a Monero wallet. Requires the `monero` library."""
    from monero.seed import Seed

    seed = Seed()
    return {
        "currency": "XMR",
        "mnemonic_seed": str(seed.phrase),
        "private_spend_key": seed.secret_spend_key(),
        "private_view_key": seed.secret_view_key(),
        "public_spend_key": seed.public_spend_key(),
        "public_view_key": seed.public_view_key(),
        "address": str(seed.public_address()),
    }
