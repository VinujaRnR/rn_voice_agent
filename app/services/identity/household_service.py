"""Household management service."""
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.database.models.identity import Household, HouseholdMembership
from app.database.repositories.user_repository import UserRepository


class HouseholdService:
    """Service handling household creation, configuration, and membership."""

    @staticmethod
    async def create_household(
        session: AsyncSession,
        creator_user_id: str,
        name: str,
        timezone: str = "Australia/Sydney",
        address: Optional[str] = None,
        city: Optional[str] = None,
        country: str = "Australia"
    ) -> Household:
        repo = UserRepository(session)
        household = await repo.create_household(
            name=name,
            timezone=timezone,
            address=address,
            city=city,
            country=country
        )
        await repo.add_household_member(
            household_id=household.id,
            user_id=creator_user_id,
            role="owner"
        )
        return household

    @staticmethod
    async def get_household(session: AsyncSession, household_id: str) -> Optional[Household]:
        repo = UserRepository(session)
        return await repo.get_household_by_id(household_id)

    @staticmethod
    async def get_user_households(session: AsyncSession, user_id: str) -> List[Household]:
        repo = UserRepository(session)
        return await repo.get_user_households(user_id)

    @staticmethod
    async def add_member(
        session: AsyncSession,
        household_id: str,
        user_id: str,
        role: str = "member"
    ) -> HouseholdMembership:
        repo = UserRepository(session)
        household = await repo.get_household_by_id(household_id)
        if not household:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Household '{household_id}' not found"
            )
        user = await repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{user_id}' not found"
            )
        return await repo.add_household_member(household_id, user_id, role)

    @staticmethod
    async def list_members(session: AsyncSession, household_id: str) -> List[HouseholdMembership]:
        repo = UserRepository(session)
        return await repo.get_household_members(household_id)

