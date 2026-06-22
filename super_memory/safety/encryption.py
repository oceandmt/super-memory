"""Memory encryption — Fernet key encryption/decryption.

Ported from neural-memory v4.58.0 safety/encryption.py.
Non-blocking: `pip install cryptography` required for use.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

logger = logging.getLogger("super-memory.safety.encryption")


class MemoryEncryptor:
    """Encrypt/decrypt memory content using Fernet symmetric encryption."""

    def __init__(self, key: bytes | None = None):
        self._fernet = None
        self._key = key
        if key is not None:
            self._init_fernet()

    def _init_fernet(self):
        try:
            from cryptography.fernet import Fernet
            if isinstance(self._key, str):
                self._key = self._key.encode()
            self._fernet = Fernet(self._key)
        except ImportError:
            logger.warning("cryptography not installed — encryption unavailable")
        except Exception as e:
            logger.warning("fernet init failed: %s", e)

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def encrypt(self, content: str) -> str:
        if not self.available:
            return content
        try:
            return self._fernet.encrypt(content.encode()).decode()
        except Exception as e:
            logger.debug("encrypt failed: %s", e)
            return content

    def decrypt(self, content: str) -> str:
        if not self.available:
            return content
        try:
            return self._fernet.decrypt(content.encode()).decode()
        except Exception as e:
            logger.debug("decrypt failed: %s", e)
            return content

    def encrypt_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self.available:
            return data
        try:
            payload = json.dumps(data, ensure_ascii=False, default=str)
            encrypted = self.encrypt(payload)
            return {"__encrypted__": True, "data": encrypted}
        except Exception:
            return data

    def decrypt_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        if not data.get("__encrypted__"):
            return data
        try:
            decrypted = self.decrypt(data.get("data", ""))
            return json.loads(decrypted)
        except Exception:
            return data

    @staticmethod
    def generate_key() -> bytes:
        try:
            from cryptography.fernet import Fernet
            return Fernet.generate_key()
        except ImportError:
            return b""  # no-op if cryptography missing


class EncryptionManager:
    """Manages encryption for memory storage with key rotation support."""

    def __init__(self, master_key: bytes | None = None):
        self._encryptors: dict[str, MemoryEncryptor] = {}
        self._active_key_id: str = "default"
        if master_key is not None:
            self.add_key("default", master_key)

    def add_key(self, key_id: str, key: bytes) -> None:
        self._encryptors[key_id] = MemoryEncryptor(key)

    def get_encryptor(self, key_id: str | None = None) -> MemoryEncryptor:
        kid = key_id or self._active_key_id
        encryptor = self._encryptors.get(kid)
        if encryptor is None:
            encryptor = MemoryEncryptor()
            self._encryptors[kid] = encryptor
        return encryptor
