"""Resident speech, wake-word, and interface preferences service."""
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.database.repositories.user_repository import UserRepository
from app.middleware.request_context import RequestContext
from app.middleware.tenant_isolation import enforce_resident_access


class PersonalizationPreferenceService:
    """Service mediating access to resident voice, audio, and UI preferences."""

    @classmethod
    async def get_resident_preferences(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        target_resident_id: str
    ) -> Dict[str, Any]:
        """Retrieve speech and persona preferences for the resident."""
        await enforce_resident_access(ctx, target_resident_id, scope="profile:read", session=session)
        repo = UserRepository(session)
        pref = await repo.get_user_preferences(target_resident_id)
        if not pref:
            # Return Sarah default persona
            return {
                "user_id": target_resident_id,
                "wake_word": "Sarah",
                "voice_name": "en-US-JennyNeural",
                "speaking_rate": 1.0,
                "volume": 1.0,
                "temperature_unit": "celsius"
            }

        return {
            "user_id": pref.user_id,
            "wake_word": pref.wake_word,
            "voice_name": pref.voice_name,
            "speaking_rate": pref.speaking_rate,
            "volume": pref.volume,
            "temperature_unit": pref.temperature_unit
        }

    @classmethod
    async def update_resident_preferences(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        target_resident_id: str,
        wake_word: Optional[str] = None,
        voice_name: Optional[str] = None,
        speaking_rate: Optional[float] = None,
        volume: Optional[float] = None,
        temperature_unit: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update resident preferences."""
        await enforce_resident_access(ctx, target_resident_id, scope="profile:write", session=session)
        repo = UserRepository(session)
        updated = await repo.upsert_user_preferences(
            user_id=target_resident_id,
            wake_word=wake_word,
            voice_name=voice_name,
            speaking_rate=speaking_rate,
            volume=volume,
            temperature_unit=temperature_unit
        )
        return {
            "user_id": updated.user_id,
            "wake_word": updated.wake_word,
            "voice_name": updated.voice_name,
            "speaking_rate": updated.speaking_rate,
            "volume": updated.volume,
            "temperature_unit": updated.temperature_unit
        }

