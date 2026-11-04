"""Application-level field encryption for sensitive data using AES-Fernet."""
import base64
import hashlib
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from app.config import settings

logger = logging.getLogger(__name__)


class FieldEncryptor:
    """Manages application-level encryption for designated database columns."""

    def __init__(self, secret_key: Optional[str] = None):
        raw_key = secret_key or settings.app_encryption_key or "sarah-default-key-32-bytes-long!"
        # Deterministically derive 32-byte urlsafe base64 key using SHA-256
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode("utf-8")).digest())
        self._fernet = Fernet(derived_key)

    def encrypt(self, plain_text: Optional[str]) -> Optional[str]:
        """Encrypt plaintext string into base64 ciphertext token."""
        if plain_text is None:
            return None
        if not plain_text:
            return ""
        try:
            return self._fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")
        except Exception as e:
            logger.error(f"Field encryption failed: {e}")
            raise

    def decrypt(self, cipher_text: Optional[str]) -> Optional[str]:
        """Decrypt ciphertext token back into plaintext string."""
        if cipher_text is None:
            return None
        if not cipher_text:
            return ""
        try:
            return self._fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # If string wasn't encrypted (e.g. legacy plain text), return as-is
            logger.debug("Field token invalid; returning raw text for backward compatibility.")
            return cipher_text
        except Exception as e:
            logger.error(f"Field decryption failed: {e}")
            return cipher_text


# Global default encryptor instance
field_encryptor = FieldEncryptor()

