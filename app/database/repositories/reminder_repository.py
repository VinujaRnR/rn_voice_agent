"""Care reminders and recurrence repository."""
from datetime import datetime, timezone
import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database.models.reminders import Reminder, RecurrenceRule, ReminderOccurrence
from app.database.base import utc_now
from app.database.repositories.base import BaseRepository


class ReminderRepository(BaseRepository[Reminder]):
    """Repository handling care reminders, recurrence rules, and occurrences."""

    def __init__(self, session: AsyncSession):
        super().__init__(Reminder, session)

    async def create_reminder(
        self,
        text: str,
        due_at_utc: datetime,
        delay_seconds: int = 0,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        recurrence: str = "once",
        reminder_id: Optional[str] = None
    ) -> Reminder:
        rem_id = reminder_id or f"rem_{uuid.uuid4().hex[:8]}"
        reminder = Reminder(
            id=rem_id,
            user_id=user_id,
            session_id=session_id,
            text=text,
            due_at_utc=due_at_utc,
            delay_seconds=delay_seconds,
            status="scheduled",
            recurrence=recurrence
        )
        self.session.add(reminder)
        await self.session.flush()
        return reminder

    async def get_active_reminders(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> List[Reminder]:
        stmt = select(Reminder).where(Reminder.status == "scheduled")
        if user_id:
            stmt = stmt.where(Reminder.user_id == user_id)
        elif session_id:
            stmt = stmt.where(Reminder.session_id == session_id)
        stmt = stmt.order_by(Reminder.due_at_utc)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def update_status(self, reminder_id: str, status: str) -> Optional[Reminder]:
        rem = await self.get_by_id(reminder_id)
        if rem:
            rem.status = status
            rem.updated_at = utc_now()
            await self.session.flush()
        return rem

    async def cancel_reminder(self, reminder_id: str) -> bool:
        rem = await self.update_status(reminder_id, "cancelled")
        return rem is not None

    async def add_recurrence_rule(
        self,
        reminder_id: str,
        frequency: str = "once",
        interval: int = 1,
        by_days: Optional[List[str]] = None,
        end_date: Optional[datetime] = None
    ) -> RecurrenceRule:
        rule = RecurrenceRule(
            reminder_id=reminder_id,
            frequency=frequency,
            interval=interval,
            by_days=by_days or [],
            end_date=end_date
        )
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def record_occurrence(
        self,
        reminder_id: str,
        scheduled_time: datetime,
        delivered_time: Optional[datetime] = None,
        status: str = "pending"
    ) -> ReminderOccurrence:
        occ = ReminderOccurrence(
            reminder_id=reminder_id,
            scheduled_time=scheduled_time,
            delivered_time=delivered_time,
            status=status
        )
        self.session.add(occ)
        await self.session.flush()
        return occ

