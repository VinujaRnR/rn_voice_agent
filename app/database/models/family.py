"""Family contacts, birthdays, anniversaries, and communication models."""
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Boolean, ForeignKey, Integer, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, utc_now
from app.database.types import EncryptedString


class FamilyContact(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Family member, emergency contact, or friend associated with a resident."""
    __tablename__ = "family_contacts"

    resident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(64), default="family", nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(EncryptedString, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_emergency_contact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_receive_alerts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class FamilyEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Recurring family birthdays, anniversaries, and scheduled family visits."""
    __tablename__ = "family_events"

    resident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    contact_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("family_contacts.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), default="birthday", nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    advance_notice_days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class FamilyMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Outbound contact requests, notifications, or call requests sent to family."""
    __tablename__ = "family_messages"

    resident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    contact_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("family_contacts.id", ondelete="SET NULL"), index=True, nullable=True
    )
    message_text: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="sent", nullable=False)
