"""Authorization, consent, and representative repository."""
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database.models.authorization import AccessGrant, ConsentRecord, Representative
from app.database.base import utc_now
from app.database.repositories.base import BaseRepository


class AuthRepository(BaseRepository[AccessGrant]):
    """Repository handling scoped access grants, consent logs, and representatives."""

    def __init__(self, session: AsyncSession):
        super().__init__(AccessGrant, session)

    async def grant_access(
        self,
        granter_id: str,
        grantee_id: str,
        scope: str,
        expires_at: Optional[datetime] = None
    ) -> AccessGrant:
        grant = AccessGrant(
            granter_id=granter_id,
            grantee_id=grantee_id,
            scope=scope,
            status="active",
            expires_at=expires_at
        )
        self.session.add(grant)
        await self.session.flush()
        return grant

    async def check_access(self, granter_id: str, grantee_id: str, scope: str) -> bool:
        stmt = (
            select(AccessGrant)
            .where(
                AccessGrant.granter_id == granter_id,
                AccessGrant.grantee_id == grantee_id,
                AccessGrant.scope == scope,
                AccessGrant.status == "active"
            )
        )
        res = await self.session.execute(stmt)
        grant = res.scalars().first()
        if not grant:
            return False
        if grant.expires_at and grant.expires_at < utc_now():
            return False
        return True

    async def revoke_access(self, grant_id: str) -> bool:
        grant = await self.get_by_id(grant_id)
        if grant:
            grant.status = "revoked"
            await self.session.flush()
            return True
        return False

    async def record_consent(
        self,
        user_id: str,
        consent_type: str,
        is_granted: bool = True
    ) -> ConsentRecord:
        record = ConsentRecord(
            user_id=user_id,
            consent_type=consent_type,
            is_granted=is_granted,
            granted_at=utc_now()
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def check_consent(self, user_id: str, consent_type: str) -> bool:
        stmt = (
            select(ConsentRecord)
            .where(
                ConsentRecord.user_id == user_id,
                ConsentRecord.consent_type == consent_type,
                ConsentRecord.is_granted == True,
                ConsentRecord.revoked_at.is_(None)
            )
            .order_by(ConsentRecord.granted_at.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalars().first() is not None

    async def add_representative(
        self,
        resident_id: str,
        representative_id: str,
        relationship_type: str,
        verified: bool = False
    ) -> Representative:
        rep = Representative(
            resident_id=resident_id,
            representative_id=representative_id,
            relationship_type=relationship_type,
            verified=verified
        )
        self.session.add(rep)
        await self.session.flush()
        return rep

