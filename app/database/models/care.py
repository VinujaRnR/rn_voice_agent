"""Caregiver, care plans, medication schedules, adherence events, and escalation models."""
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Boolean, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, utc_now
from app.database.types import JSONType, EncryptedString, EncryptedText


class Caregiver(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Caregiver professional details linked to a user account."""
    __tablename__ = "caregivers"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    agency_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    license_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    specialty: Mapped[str] = mapped_column(String(64), default="elderly_care", nullable=False)


class CaregiverAssignment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Scoped care assignment linking caregiver to an elderly resident."""
    __tablename__ = "caregiver_assignments"

    caregiver_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("caregivers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    resident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scope: Mapped[str] = mapped_column(String(64), default="full_care", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CarePlan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Resident care instructions, dietary requirements, and daily routine."""
    __tablename__ = "care_plans"

    resident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    routine_details: Mapped[Dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    dietary_notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    emergency_instructions: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)


class MedicationSchedule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Prescription schedule specifying drug name, exact dosage, and required timing."""
    __tablename__ = "medication_schedules"

    resident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    medication_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dosage: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_time: Mapped[str] = mapped_column(String(16), nullable=False)  # e.g. "08:00", "20:00"
    instructions: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    requires_food: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MedicationEvent(Base, UUIDPrimaryKeyMixin):
    """Tracks discrete stages: reminded, acknowledged, dispenser_removed, caregiver_confirmed, missed."""
    __tablename__ = "medication_events"

    schedule_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("medication_schedules.id", ondelete="CASCADE"), index=True, nullable=False
    )
    resident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class CareEscalation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Safety or adherence escalation alert dispatched to caregivers/representatives."""
    __tablename__ = "care_escalations"

    resident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    incident_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    details: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
