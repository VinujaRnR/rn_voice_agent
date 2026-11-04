"""Custom SQLAlchemy column types including application-level encrypted fields."""
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy import TypeDecorator, String, Text, DateTime, JSON
from app.database.encryption import field_encryptor


class EncryptedString(TypeDecorator):
    """Encrypted string column using application-level AES-Fernet encryption."""
    impl = String(512)
    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        return field_encryptor.encrypt(str(value))

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        return field_encryptor.decrypt(value)


class EncryptedText(TypeDecorator):
    """Encrypted text column for long strings using application-level AES-Fernet encryption."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        return field_encryptor.encrypt(str(value))

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        return field_encryptor.decrypt(value)


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC DateTime column ensuring consistent timezone handling."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


JSONType = JSON

