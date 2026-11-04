"""Family contacts, events, and communications repository."""
from typing import Optional, List
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models.family import FamilyContact, FamilyEvent, FamilyMessage
from app.database.repositories.base import BaseRepository


class FamilyRepository(BaseRepository[FamilyContact]):
    """Repository handling family directories, birthdays, and communications."""

    def __init__(self, session: AsyncSession):
        super().__init__(FamilyContact, session)

    async def add_contact(
        self,
        resident_id: str,
        name: str,
        relationship_type: str = "family",
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
        is_emergency_contact: bool = False,
        can_receive_alerts: bool = True,
        notes: Optional[str] = None
    ) -> FamilyContact:
        contact = FamilyContact(
            resident_id=resident_id,
            name=name,
            relationship_type=relationship_type,
            phone_number=phone_number,
            email=email,
            is_emergency_contact=is_emergency_contact,
            can_receive_alerts=can_receive_alerts,
            notes=notes
        )
        self.session.add(contact)
        await self.session.flush()
        return contact

    async def list_contacts(self, resident_id: str) -> List[FamilyContact]:
        stmt = select(FamilyContact).where(FamilyContact.resident_id == resident_id)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def add_event(
        self,
        resident_id: str,
        title: str,
        event_date: date,
        event_type: str = "birthday",
        contact_id: Optional[str] = None,
        advance_notice_days: int = 1
    ) -> FamilyEvent:
        evt = FamilyEvent(
            resident_id=resident_id,
            contact_id=contact_id,
            title=title,
            event_type=event_type,
            event_date=event_date,
            advance_notice_days=advance_notice_days
        )
        self.session.add(evt)
        await self.session.flush()
        return evt

    async def list_events(self, resident_id: str) -> List[FamilyEvent]:
        stmt = select(FamilyEvent).where(FamilyEvent.resident_id == resident_id)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def record_message(
        self,
        resident_id: str,
        message_text: str,
        contact_id: Optional[str] = None,
        status: str = "sent"
    ) -> FamilyMessage:
        msg = FamilyMessage(
            resident_id=resident_id,
            contact_id=contact_id,
            message_text=message_text,
            status=status
        )
        self.session.add(msg)
        await self.session.flush()
        return msg
