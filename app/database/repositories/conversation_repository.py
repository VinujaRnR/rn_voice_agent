"""Conversation, session, cryptographic message log, and pending action repository."""
import hashlib
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, desc
from app.database.models.conversation import Session, ConversationMessage, PendingAction
from app.database.base import utc_now
from app.database.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Session]):
    """Repository handling conversational persistence."""

    def __init__(self, session: AsyncSession):
        super().__init__(Session, session)

    async def get_or_create_session(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        household_id: Optional[str] = None
    ) -> Session:
        db_sess = await self.get_by_id(session_id)
        if not db_sess:
            db_sess = Session(
                id=session_id,
                user_id=user_id,
                household_id=household_id,
                is_active=True,
                is_awake=False,
                last_activity_at=utc_now()
            )
            self.session.add(db_sess)
            await self.session.flush()
        else:
            db_sess.last_activity_at = utc_now()
            if user_id and not db_sess.user_id:
                db_sess.user_id = user_id
            if household_id and not db_sess.household_id:
                db_sess.household_id = household_id
            await self.session.flush()
        return db_sess

    async def touch_session(self, session_id: str, is_awake: Optional[bool] = None) -> Optional[Session]:
        db_sess = await self.get_by_id(session_id)
        if db_sess:
            db_sess.last_activity_at = utc_now()
            if is_awake is not None:
                db_sess.is_awake = is_awake
            await self.session.flush()
        return db_sess

    async def add_message(
        self,
        session_id: str,
        sender: str,
        content: str,
        user_id: Optional[str] = None
    ) -> ConversationMessage:
        # Fetch the most recent message in the session to chain cryptographic hashes
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(desc(ConversationMessage.seq_num), desc(ConversationMessage.created_at))
            .limit(1)
        )
        res = await self.session.execute(stmt)
        last_msg = res.scalars().first()

        prev_hash = last_msg.content_hash if last_msg else None
        seq_num = (last_msg.seq_num + 1) if last_msg else 1

        content_clean = content.strip()
        chain_input = f"{prev_hash or ''}:{sender}:{content_clean}"
        content_hash = hashlib.sha256(chain_input.encode("utf-8")).hexdigest()

        msg = ConversationMessage(
            session_id=session_id,
            user_id=user_id,
            sender=sender,
            content=content_clean,
            content_hash=content_hash,
            prev_hash=prev_hash,
            seq_num=seq_num
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def get_messages(self, session_id: str, limit: int = 50) -> List[ConversationMessage]:
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.seq_num)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def clear_messages(self, session_id: str, user_id: Optional[str] = None) -> int:
        stmt = delete(ConversationMessage).where(ConversationMessage.session_id == session_id)
        if user_id:
            stmt = stmt.where(ConversationMessage.user_id == user_id)
        res = await self.session.execute(stmt)
        await self.session.flush()
        return res.rowcount or 0

    async def save_pending_action(
        self,
        session_id: str,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
        missing_fields: Optional[List[str]] = None
    ) -> PendingAction:
        pending = PendingAction(
            session_id=session_id,
            action=action,
            parameters=parameters or {},
            missing_fields=missing_fields or [],
            status="pending"
        )
        self.session.add(pending)
        await self.session.flush()
        return pending

    async def get_pending_action(self, session_id: str) -> Optional[PendingAction]:
        stmt = (
            select(PendingAction)
            .where(PendingAction.session_id == session_id, PendingAction.status == "pending")
            .order_by(desc(PendingAction.created_at))
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def resolve_pending_action(self, session_id: str) -> bool:
        stmt = (
            update(PendingAction)
            .where(PendingAction.session_id == session_id, PendingAction.status == "pending")
            .values(status="resolved", updated_at=utc_now())
        )
        res = await self.session.execute(stmt)
        await self.session.flush()
        return (res.rowcount or 0) > 0

    async def cancel_pending_action(self, session_id: str) -> bool:
        stmt = (
            update(PendingAction)
            .where(PendingAction.session_id == session_id, PendingAction.status == "pending")
            .values(status="cancelled", updated_at=utc_now())
        )
        res = await self.session.execute(stmt)
        await self.session.flush()
        return (res.rowcount or 0) > 0

