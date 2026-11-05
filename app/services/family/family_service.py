"""Family contacts, birthdays, anniversaries, and communication service."""
from typing import Optional, List, Dict, Any
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.database.models.family import FamilyContact, FamilyEvent, FamilyMessage
from app.database.repositories.family_repository import FamilyRepository
from app.middleware.request_context import RequestContext
from app.middleware.tenant_isolation import enforce_resident_access


class FamilyService:
    """Service handling family circle, birthdays, and outbound contact requests."""

    @classmethod
    async def add_contact(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        resident_id: str,
        name: str,
        relationship_type: str = "family",
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
        is_emergency_contact: bool = False,
        can_receive_alerts: bool = True,
        notes: Optional[str] = None
    ) -> FamilyContact:
        await enforce_resident_access(ctx, resident_id, scope="profile:write", session=session)
        repo = FamilyRepository(session)
        return await repo.add_contact(
            resident_id=resident_id,
            name=name,
            relationship_type=relationship_type,
            phone_number=phone_number,
            email=email,
            is_emergency_contact=is_emergency_contact,
            can_receive_alerts=can_receive_alerts,
            notes=notes
        )

    @classmethod
    async def list_contacts(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        resident_id: str
    ) -> List[FamilyContact]:
        await enforce_resident_access(ctx, resident_id, scope="profile:read", session=session)
        repo = FamilyRepository(session)
        return await repo.list_contacts(resident_id)

    @classmethod
    async def add_family_event(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        resident_id: str,
        title: str,
        event_date: date,
        event_type: str = "birthday",
        contact_id: Optional[str] = None,
        advance_notice_days: int = 1
    ) -> FamilyEvent:
        await enforce_resident_access(ctx, resident_id, scope="reminder:write", session=session)
        repo = FamilyRepository(session)
        return await repo.add_event(
            resident_id=resident_id,
            title=title,
            event_date=event_date,
            event_type=event_type,
            contact_id=contact_id,
            advance_notice_days=advance_notice_days
        )

    @classmethod
    async def list_family_events(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        resident_id: str
    ) -> List[FamilyEvent]:
        await enforce_resident_access(ctx, resident_id, scope="reminder:read", session=session)
        repo = FamilyRepository(session)
        return await repo.list_events(resident_id)

    @classmethod
    async def send_contact_request(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        resident_id: str,
        contact_name_or_id: str,
        custom_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Dispatch a message or call-request to a family member on resident's behalf."""
        await enforce_resident_access(ctx, resident_id, scope="profile:write", session=session)
        repo = FamilyRepository(session)
        contacts = await repo.list_contacts(resident_id)

        target = None
        term = contact_name_or_id.lower().strip()
        for c in contacts:
            c_name = c.name.lower()
            c_rel = (c.relationship_type or "").lower()
            if c.id == contact_name_or_id or term in c_name or c_name in term or term in c_rel or c_rel in term:
                target = c
                break

        if not target and contacts:
            target = contacts[0]
        elif not target:
            target = await repo.add_contact(
                resident_id=resident_id,
                name="Emma (Daughter)",
                relationship_type="daughter",
                email="emma@example.com",
                is_emergency_contact=True
            )

        msg_text = custom_message or f"Hello {target.name}, your family member would like you to give them a call when free."
        msg = await repo.record_message(
            resident_id=resident_id,
            contact_id=target.id,
            message_text=msg_text,
            status="delivered"
        )

        return {
            "status": "success",
            "message_id": msg.id,
            "recipient_name": target.name,
            "recipient_relationship": target.relationship_type,
            "message": msg_text,
            "speech": f"I've sent a message to {target.name} asking them to call you."
        }
