"""Radar sensor safety events, fall detection, and Australian alerts service."""
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.safety import SensorEvent, SafetyRule, SafetyIncident, ExternalAlert
from app.database.repositories.safety_repository import SafetyRepository
from app.middleware.request_context import RequestContext
from app.middleware.tenant_isolation import enforce_household_isolation


class SafetyService:
    """Service handling non-intrusive radar safety detection and Australian emergency alerts."""

    VALID_SENSOR_CATEGORIES = {
        "possible_fall", "unusual_inactivity", "room_presence", "bed_exit", "device_disconnected"
    }

    @classmethod
    async def process_sensor_event(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        household_id: str,
        event_category: str,
        confidence: float = 1.0,
        device_id: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Ingest radar event and trigger appropriate safety rules or caregiver escalation."""
        enforce_household_isolation(ctx, household_id)
        repo = SafetyRepository(session)

        evt = await repo.log_sensor_event(
            household_id=household_id,
            event_category=event_category,
            confidence=confidence,
            device_id=device_id,
            metadata_json=metadata_json
        )

        incident = None
        # If fall detected with high confidence (>0.7), create incident for verification
        if event_category == "possible_fall" and confidence >= 0.7:
            incident = await repo.create_safety_incident(
                household_id=household_id,
                resident_id=ctx.resident_id,
                incident_type="possible_fall_detected",
                severity="high",
                details={
                    "sensor_event_id": evt.id,
                    "confidence": confidence,
                    "device_id": device_id
                }
            )

        return {
            "status": "success",
            "event_id": evt.id,
            "category": evt.event_category,
            "incident_created": incident is not None,
            "incident_id": incident.id if incident else None
        }

    @classmethod
    async def list_sensor_events(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        household_id: str
    ) -> List[SensorEvent]:
        enforce_household_isolation(ctx, household_id)
        repo = SafetyRepository(session)
        return await repo.list_sensor_events(household_id)

    @classmethod
    async def publish_external_alert(
        cls,
        session: AsyncSession,
        source: str,
        alert_type: str,
        severity: str,
        headline: str,
        region: str,
        expires_at: datetime
    ) -> ExternalAlert:
        repo = SafetyRepository(session)
        return await repo.create_external_alert(
            source=source,
            alert_type=alert_type,
            severity=severity,
            headline=headline,
            region=region,
            expires_at=expires_at
        )

    @classmethod
    async def get_active_alerts(
        cls,
        session: AsyncSession,
        region: Optional[str] = None
    ) -> List[ExternalAlert]:
        repo = SafetyRepository(session)
        return await repo.get_active_external_alerts(region)
