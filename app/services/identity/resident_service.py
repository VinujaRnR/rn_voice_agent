"""Resident care profile service."""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.database.models.identity import ResidentProfile
from app.database.repositories.user_repository import UserRepository


class ResidentService:
    """Service managing elderly resident profiles and medical/emergency contacts."""

    @staticmethod
    async def get_profile(session: AsyncSession, user_id: str) -> Optional[ResidentProfile]:
        repo = UserRepository(session)
        return await repo.get_resident_profile(user_id)

    @staticmethod
    async def update_profile(
        session: AsyncSession,
        user_id: str,
        preferred_name: Optional[str] = None,
        birth_year: Optional[int] = None,
        medical_notes: Optional[str] = None,
        emergency_contact_phone: Optional[str] = None,
        primary_language: Optional[str] = None,
        household_id: Optional[str] = None
    ) -> ResidentProfile:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resident user '{user_id}' not found"
            )

        return await repo.upsert_resident_profile(
            user_id=user_id,
            household_id=household_id,
            preferred_name=preferred_name,
            birth_year=birth_year,
            medical_notes=medical_notes,
            emergency_contact_phone=emergency_contact_phone,
            primary_language=primary_language or "en"
        )

