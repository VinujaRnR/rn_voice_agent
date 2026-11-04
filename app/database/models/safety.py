"""Radar-based elderly safety, sensor events, and Australian emergency alerts models."""
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import String, Boolean, ForeignKey, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, utc_now
from app.database.types import JSONType


class SensorEvent(Base, UUIDPrimaryKeyMixin):
    """Privacy-preserving radar or environmental sensor event."""
    __tablename__ = "sensor_events"

    device_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    household_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("households.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_category: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(default=utc_now, index=True, nullable=False)


class SafetyRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Configurable household safety rule (inactivity limits, bed exit thresholds)."""
    __tablename__ = "safety_rules"

    household_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("households.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    event_category: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    action: Mapped[str] = mapped_column(String(64), default="alert_caregiver", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SafetyIncident(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Triggered safety event requiring verification or escalation."""
    __tablename__ = "safety_incidents"

    household_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("households.id", ondelete="CASCADE"), index=True, nullable=False
    )
    resident_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    incident_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


class ExternalAlert(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Official Australian weather or civil emergency hazard notification."""
    __tablename__ = "external_alerts"

    source: Mapped[str] = mapped_column(String(64), default="BOM", nullable=False)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="warning", nullable=False)
    headline: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
