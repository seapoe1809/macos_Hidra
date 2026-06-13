"""Encrypted secrets vault (Fernet + PBKDF2).

Condensed from secret_manager_sample.py into a reusable class. Used to store
provider-side secrets (e.g. the BTC view key, login token) encrypted at rest.
File layout: first 16 bytes = salt, remainder = Fernet ciphertext.
"""

import os
import json
import base64
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptedVault:
    def __init__(self, path: str = "secrets.enc"):
        self.path = Path(path)
        self._fernet: Fernet | None = None
        self.secrets: dict = {}

    def _fernet_for(self, password: str, salt: bytes) -> Fernet:
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
        return Fernet(base64.urlsafe_b64encode(kdf.derive(password.encode())))

    def unlock(self, password: str) -> bool:
        """Create the vault if missing, else decrypt it. Returns success."""
        if not self.path.exists():
            salt = os.urandom(16)
            self._fernet = self._fernet_for(password, salt)
            self.secrets = {}
            self._save(salt)
            return True
        try:
            data = self.path.read_bytes()
            salt, blob = data[:16], data[16:]
            self._fernet = self._fernet_for(password, salt)
            self.secrets = json.loads(self._fernet.decrypt(blob).decode())
            return True
        except Exception:
            return False

    def _save(self, salt: bytes):
        blob = self._fernet.encrypt(json.dumps(self.secrets, indent=2).encode())
        self.path.write_bytes(salt + blob)

    def set(self, key: str, value: str):
        self.secrets[key] = value
        salt = self.path.read_bytes()[:16]
        self._save(salt)

    def get(self, key: str):
        return self.secrets.get(key)

    def keys(self) -> list[str]:
        return list(self.secrets.keys())
