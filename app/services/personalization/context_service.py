"""Context aggregation service for Sarah conversational reasoning and persona adaptation."""
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.request_context import RequestContext
from app.services.personalization.profile_service import PersonalizationProfileService
from app.services.personalization.preference_service import PersonalizationPreferenceService
from app.services.personalization.memory_service import PersonalizationMemoryService
from app.database.repositories.user_repository import UserRepository


class PersonalizationContextService:
    """Aggregates authorized profile, preferences, household, and memory context for Sarah."""

    @classmethod
    async def get_authorized_context(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        target_resident_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Produce consolidated context for conversational prompt generation."""
        resident_id = target_resident_id or ctx.resident_id or ctx.actor_id

        # 1. Profile
        profile_data = {}
        try:
            profile_data = await PersonalizationProfileService.get_authorized_profile(
                session=session,
                ctx=ctx,
                target_resident_id=resident_id
            )
        except Exception:
            profile_data = {
                "preferred_name": "Resident",
                "primary_language": "en",
                "medical_notes": None
            }

        # 2. Preferences
        pref_data = await PersonalizationPreferenceService.get_resident_preferences(
            session=session,
            ctx=ctx,
            target_resident_id=resident_id
        )

        # 3. Memories
        memories = []
        try:
            memories = await PersonalizationMemoryService.get_authorized_memories(
                session=session,
                ctx=ctx,
                target_resident_id=resident_id
            )
        except Exception:
            memories = []

        # 4. Household info
        household_info = {}
        household_id = profile_data.get("household_id") or ctx.household_id
        if household_id:
            repo = UserRepository(session)
            hh = await repo.get_household_by_id(household_id)
            if hh:
                household_info = {
                    "id": hh.id,
                    "name": hh.name,
                    "timezone": hh.timezone,
                    "city": hh.city,
                    "country": hh.country
                }

        return {
            "resident_id": resident_id,
            "preferred_name": profile_data.get("preferred_name") or "Resident",
            "language": profile_data.get("primary_language", "en"),
            "medical_notes": profile_data.get("medical_notes"),
            "household": household_info,
            "preferences": pref_data,
            "memories": memories[:10]  # Top 10 most relevant/important memories
        }

