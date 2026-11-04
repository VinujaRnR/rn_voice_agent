"""Household membership and role assignments service."""
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.database.models.identity import HouseholdMembership
from app.database.repositories.user_repository import UserRepository


class MembershipService:
    """Service managing user roles and memberships across households."""

    VALID_ROLES = {"owner", "admin", "resident", "family", "caregiver", "member"}

    @classmethod
    async def assign_role(
        cls,
        session: AsyncSession,
        household_id: str,
        user_id: str,
        role: str
    ) -> HouseholdMembership:
        if role not in cls.VALID_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid household role '{role}'. Valid roles: {cls.VALID_ROLES}"
            )

        repo = UserRepository(session)
        members = await repo.get_household_members(household_id)
        for m in members:
            if m.user_id == user_id:
                m.role = role
                await session.flush()
                return m

        return await repo.add_household_member(household_id=household_id, user_id=user_id, role=role)

