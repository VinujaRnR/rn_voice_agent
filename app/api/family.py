"""Family contacts, birthdays, and communications API."""
from typing import Optional, List, Dict, Any
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database.session import get_db_session, transaction
from app.middleware.request_context import RequestContext, get_request_context
from app.middleware.authorization import require_authenticated, require_permission
from app.services.family.family_service import FamilyService

router = APIRouter(prefix="/api/v1/family", tags=["Family Services"])


class FamilyContactCreate(BaseModel):
    resident_id: Optional[str] = None
    name: str = Field(..., description="Contact name, e.g. 'Emma'")
    relationship_type: str = Field("daughter", description="Relationship: son, daughter, spouse, friend")
    phone_number: Optional[str] = None
    email: Optional[str] = None
    is_emergency_contact: bool = False
    can_receive_alerts: bool = True
    notes: Optional[str] = None


class FamilyEventCreate(BaseModel):
    resident_id: Optional[str] = None
    title: str = Field(..., description="Event title, e.g. 'Emma Birthday'")
    event_date: date = Field(..., description="Event date (YYYY-MM-DD)")
    event_type: str = Field("birthday", description="Event type: birthday, anniversary, visit")
    contact_id: Optional[str] = None
    advance_notice_days: int = Field(1, ge=0, le=30)


class ContactRequestCreate(BaseModel):
    resident_id: Optional[str] = None
    contact_name_or_id: str = Field(..., description="Contact name (e.g. 'son', 'Emma') or contact ID")
    custom_message: Optional[str] = None


@router.post("/contacts", status_code=status.HTTP_201_CREATED)
async def add_contact(
    payload: FamilyContactCreate,
    ctx: RequestContext = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session)
):
    target_res = payload.resident_id or ctx.resident_id or ctx.actor_id
    async with transaction(session):
        contact = await FamilyService.add_contact(
            session=session,
            ctx=ctx,
            resident_id=target_res,
            name=payload.name,
            relationship_type=payload.relationship_type,
            phone_number=payload.phone_number,
            email=payload.email,
            is_emergency_contact=payload.is_emergency_contact,
            can_receive_alerts=payload.can_receive_alerts,
            notes=payload.notes
        )
    return {
        "status": "success",
        "id": contact.id,
        "name": contact.name,
        "relationship_type": contact.relationship_type,
        "is_emergency_contact": contact.is_emergency_contact
    }


@router.get("/contacts")
async def list_contacts(
    resident_id: Optional[str] = None,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    target_res = resident_id or ctx.resident_id or ctx.actor_id
    contacts = await FamilyService.list_contacts(session=session, ctx=ctx, resident_id=target_res)
    return [
        {
            "id": c.id,
            "name": c.name,
            "relationship_type": c.relationship_type,
            "phone_number": c.phone_number,
            "email": c.email,
            "is_emergency_contact": c.is_emergency_contact
        }
        for c in contacts
    ]


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def add_event(
    payload: FamilyEventCreate,
    ctx: RequestContext = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session)
):
    target_res = payload.resident_id or ctx.resident_id or ctx.actor_id
    async with transaction(session):
        event = await FamilyService.add_family_event(
            session=session,
            ctx=ctx,
            resident_id=target_res,
            title=payload.title,
            event_date=payload.event_date,
            event_type=payload.event_type,
            contact_id=payload.contact_id,
            advance_notice_days=payload.advance_notice_days
        )
    return {
        "status": "success",
        "id": event.id,
        "title": event.title,
        "event_date": event.event_date.isoformat(),
        "event_type": event.event_type
    }


@router.get("/events")
async def list_events(
    resident_id: Optional[str] = None,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    target_res = resident_id or ctx.resident_id or ctx.actor_id
    events = await FamilyService.list_family_events(session=session, ctx=ctx, resident_id=target_res)
    return [
        {
            "id": e.id,
            "title": e.title,
            "event_date": e.event_date.isoformat(),
            "event_type": e.event_type,
            "advance_notice_days": e.advance_notice_days
        }
        for e in events
    ]


@router.post("/contact-requests")
async def send_contact_request(
    payload: ContactRequestCreate,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    target_res = payload.resident_id or ctx.resident_id or ctx.actor_id or "default_resident"
    async with transaction(session):
        res = await FamilyService.send_contact_request(
            session=session,
            ctx=ctx,
            resident_id=target_res,
            contact_name_or_id=payload.contact_name_or_id,
            custom_message=payload.custom_message
        )
    return res
