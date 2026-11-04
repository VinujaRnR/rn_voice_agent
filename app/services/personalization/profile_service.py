"""Authorized resident profile retrieval and update service."""
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.database.repositories.user_repository import UserRepository
from app.middleware.request_context import RequestContext
from app.middleware.tenant_isolation import enforce_household_isolation, enforce_resident_access
from app.middleware.consent import verify_resident_consent


class PersonalizationProfileService:
    """Service mediating access to resident profile and care information."""

    @classmethod
    async def get_authorized_profile(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        target_resident_id: str
    ) -> Dict[str, Any]:
        """Fetch resident profile with tenant boundary, access grant, and consent verification.
        
        If a caregiver/family member requests the profile, checks 'medical_data' consent
        before revealing sensitive medical notes.
        """
        repo = UserRepository(session)
        profile = await repo.get_resident_profile(target_resident_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resident profile for '{target_resident_id}' not found"
            )

        # Enforce tenant isolation if profile is associated with a household
        enforce_household_isolation(ctx, profile.household_id)

        # Enforce resident access permissions / access grant
        await enforce_resident_access(
            ctx=ctx,
            target_resident_id=target_resident_id,
            scope="profile:read",
            session=session
        )

        # Redact medical notes if medical consent is not granted
        medical_notes = profile.medical_notes
        if ctx.actor_id != target_resident_id and not ctx.is_legacy and ctx.role != "admin":
            has_medical_consent = await verify_resident_consent(
                session=session,
                user_id=target_resident_id,
                consent_type="medical_data",
                allow_default_if_unrecorded=False
            )
            if not has_medical_consent:
                medical_notes = "[REDACTED: Consent required]"

        return {
            "id": profile.id,
            "user_id": profile.user_id,
            "household_id": profile.household_id,
            "preferred_name": profile.preferred_name,
            "birth_year": profile.birth_year,
            "primary_language": profile.primary_language,
            "medical_notes": medical_notes,
            "emergency_contact_phone": profile.emergency_contact_phone
        }

    @classmethod
    async def update_authorized_profile(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        target_resident_id: str,
        preferred_name: Optional[str] = None,
        birth_year: Optional[int] = None,
        medical_notes: Optional[str] = None,
        emergency_contact_phone: Optional[str] = None,
        primary_language: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update resident profile ensuring actor has profile:write permissions."""
        repo = UserRepository(session)
        profile = await repo.get_resident_profile(target_resident_id)
        if profile and profile.household_id:
            enforce_household_isolation(ctx, profile.household_id)

        await enforce_resident_access(
            ctx=ctx,
            target_resident_id=target_resident_id,
            scope="profile:write",
            session=session
        )

        updated = await repo.upsert_resident_profile(
            user_id=target_resident_id,
            household_id=profile.household_id if profile else ctx.household_id,
            preferred_name=preferred_name,
            birth_year=birth_year,
            medical_notes=medical_notes,
            emergency_contact_phone=emergency_contact_phone,
            primary_language=primary_language or "en"
        )
        return {
            "id": updated.id,
            "user_id": updated.user_id,
            "household_id": updated.household_id,
            "preferred_name": updated.preferred_name,
            "birth_year": updated.birth_year,
            "primary_language": updated.primary_language,
            "medical_notes": updated.medical_notes,
            "emergency_contact_phone": updated.emergency_contact_phone
        }

