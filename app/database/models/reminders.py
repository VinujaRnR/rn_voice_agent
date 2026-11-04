"""Care reminders, recurrence rules, and occurrence tracking models."""
from datetime import datetime, timezone
import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, ForeignKey, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, utc_now
from app.database.types import JSONType


class Reminder(Base, TimestampMixin):
    """Core care reminder entity."""
    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: f"rem_{uuid.uuid4().hex[:8]}",
        index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    session_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="SET NULL"), index=True, nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    due_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    delay_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="scheduled", index=True, nullable=False)
    recurrence: Mapped[str] = mapped_column(String(32), default="once", nullable=False)

    # Relationships
    recurrence_rules: Mapped[List["RecurrenceRule"]] = relationship(
        "RecurrenceRule", back_populates="reminder", cascade="all, delete-orphan"
    )
    occurrences: Mapped[List["ReminderOccurrence"]] = relationship(
        "ReminderOccurrence", back_populates="reminder", cascade="all, delete-orphan"
    )


class RecurrenceRule(Base, UUIDPrimaryKeyMixin):
    """Detailed recurrence specification for repeated care tasks."""
    __tablename__ = "recurrence_rules"

    reminder_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("reminders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    frequency: Mapped[str] = mapped_column(String(32), default="once", nullable=False)
    interval: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    by_days: Mapped[Optional[List[str]]] = mapped_column(JSONType, nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)

    # Relationships
    reminder: Mapped["Reminder"] = relationship("Reminder", back_populates="recurrence_rules")


class ReminderOccurrence(Base, UUIDPrimaryKeyMixin):
    """Execution delivery log for an occurrence of a reminder."""
    __tablename__ = "reminder_occurrences"

    reminder_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("reminders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    delivered_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    reminder: Mapped["Reminder"] = relationship("Reminder", back_populates="occurrences")

