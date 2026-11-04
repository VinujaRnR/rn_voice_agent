"""Radar safety events, rules, incidents, and Australian external alerts repository."""
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models.safety import SensorEvent, SafetyRule, SafetyIncident, ExternalAlert
from app.database.repositories.base import BaseRepository
from app.database.base import utc_now


class SafetyRepository(BaseRepository[SensorEvent]):
    """Repository handling radar sensor telemetry, safety rules, incidents, and emergency feeds."""

    def __init__(self, session: AsyncSession):
        super().__init__(SensorEvent, session)

    async def log_sensor_event(
        self,
        household_id: str,
        event_category: str,
        confidence: float = 1.0,
        device_id: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None
    ) -> SensorEvent:
        evt = SensorEvent(
            household_id=household_id,
            device_id=device_id,
            event_category=event_category,
            confidence=confidence,
            metadata_json=metadata_json or {}
        )
        self.session.add(evt)
        await self.session.flush()
        return evt

    async def list_sensor_events(self, household_id: str, limit: int = 50) -> List[SensorEvent]:
        stmt = (
            select(SensorEvent)
            .where(SensorEvent.household_id == household_id)
            .order_by(SensorEvent.recorded_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def create_safety_rule(
        self,
        household_id: str,
        rule_name: str,
        event_category: str,
        threshold_minutes: int = 60,
        action: str = "alert_caregiver"
    ) -> SafetyRule:
        rule = SafetyRule(
            household_id=household_id,
            rule_name=rule_name,
            event_category=event_category,
            threshold_minutes=threshold_minutes,
            action=action
        )
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def create_safety_incident(
        self,
        household_id: str,
        incident_type: str,
        severity: str = "medium",
        resident_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> SafetyIncident:
        inc = SafetyIncident(
            household_id=household_id,
            resident_id=resident_id,
            incident_type=incident_type,
            severity=severity,
            status="open",
            details=details or {}
        )
        self.session.add(inc)
        await self.session.flush()
        return inc

    async def create_external_alert(
        self,
        source: str,
        alert_type: str,
        severity: str,
        headline: str,
        region: str,
        expires_at: datetime
    ) -> ExternalAlert:
        alert = ExternalAlert(
            source=source,
            alert_type=alert_type,
            severity=severity,
            headline=headline,
            region=region,
            expires_at=expires_at
        )
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def get_active_external_alerts(self, region: Optional[str] = None) -> List[ExternalAlert]:
        stmt = select(ExternalAlert).where(ExternalAlert.expires_at > utc_now())
        if region:
            stmt = stmt.where(ExternalAlert.region == region)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
