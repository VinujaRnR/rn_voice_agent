"""Radar safety events and Australian hazard alerts API."""
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database.session import get_db_session, transaction
from app.middleware.request_context import RequestContext, get_request_context
from app.services.safety.safety_service import SafetyService

router = APIRouter(prefix="/api/v1/safety", tags=["Elderly Safety & Radar"])


class SensorEventCreate(BaseModel):
    household_id: Optional[str] = None
    event_category: str = Field(..., description="possible_fall, unusual_inactivity, room_presence, bed_exit")
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    device_id: Optional[str] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict)


class ExternalAlertCreate(BaseModel):
    source: str = "BOM"
    alert_type: str = "severe_weather"
    severity: str = "warning"
    headline: str
    region: str = "NSW"
    expires_at: datetime


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def record_sensor_event(
    payload: SensorEventCreate,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    target_hh = payload.household_id or ctx.household_id
    if not target_hh:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Household ID is required")

    async with transaction(session):
        res = await SafetyService.process_sensor_event(
            session=session,
            ctx=ctx,
            household_id=target_hh,
            event_category=payload.event_category,
            confidence=payload.confidence,
            device_id=payload.device_id,
            metadata_json=payload.metadata_json
        )
    return res


@router.get("/events")
async def list_sensor_events(
    household_id: Optional[str] = None,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    target_hh = household_id or ctx.household_id
    if not target_hh:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Household ID is required")

    events = await SafetyService.list_sensor_events(session=session, ctx=ctx, household_id=target_hh)
    return [
        {
            "id": e.id,
            "category": e.event_category,
            "confidence": e.confidence,
            "device_id": e.device_id,
            "recorded_at": e.recorded_at.isoformat()
        }
        for e in events
    ]


@router.post("/alerts", status_code=status.HTTP_201_CREATED)
async def create_external_alert(
    payload: ExternalAlertCreate,
    session: AsyncSession = Depends(get_db_session)
):
    async with transaction(session):
        alert = await SafetyService.publish_external_alert(
            session=session,
            source=payload.source,
            alert_type=payload.alert_type,
            severity=payload.severity,
            headline=payload.headline,
            region=payload.region,
            expires_at=payload.expires_at
        )
    return {
        "status": "success",
        "id": alert.id,
        "source": alert.source,
        "headline": alert.headline,
        "region": alert.region
    }


@router.get("/alerts")
async def list_alerts(
    region: Optional[str] = Query(None, description="Optional state or suburb (e.g. NSW, VIC)"),
    session: AsyncSession = Depends(get_db_session)
):
    alerts = await SafetyService.get_active_alerts(session=session, region=region)
    return [
        {
            "id": a.id,
            "source": a.source,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "headline": a.headline,
            "region": a.region,
            "expires_at": a.expires_at.isoformat()
        }
        for a in alerts
    ]
