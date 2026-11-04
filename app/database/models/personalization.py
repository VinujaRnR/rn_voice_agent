"""Personalization models: user preferences and encrypted long-term personal memories."""
from typing import Optional
from sqlalchemy import String, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, UUIDPrimaryKeyMixin, TimestampMixin
from app.database.types import EncryptedText


class UserPreference(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Resident and user interface preferences."""
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    wake_word: Mapped[str] = mapped_column(String(64), default="Sarah", nullable=False)
    voice_name: Mapped[str] = mapped_column(String(64), default="en-US-JennyNeural", nullable=False)
    speaking_rate: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    volume: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    temperature_unit: Mapped[str] = mapped_column(String(16), default="celsius", nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="preferences")


class PersonalMemory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Encrypted long-term memory item associated with a specific resident."""
    __tablename__ = "personal_memories"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    memory_key: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    memory_value: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="general", index=True, nullable=False)
    importance_score: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User")

