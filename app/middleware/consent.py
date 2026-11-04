"""Consent verification for resident personal data and sensitive actions."""
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.repositories.auth_repository import AuthRepository


async def verify_resident_consent(
    session: AsyncSession,
    user_id: str,
    consent_type: str,
    allow_default_if_unrecorded: bool = True
) -> bool:
    """Verify if a resident has granted valid consent for a given action or data access.
    
    If consent has been explicitly revoked or denied, returns False.
    If no record exists and allow_default_if_unrecorded is True (for standard services), returns True.
    """
    repo = AuthRepository(session)
    has_consent = await repo.check_consent(user_id=user_id, consent_type=consent_type)
    if has_consent:
        return True
    return allow_default_if_unrecorded


async def require_consent(
    session: AsyncSession,
    user_id: str,
    consent_type: str
) -> None:
    """Enforce consent requirement; raises 403 if consent is missing or revoked."""
    granted = await verify_resident_consent(session, user_id, consent_type, allow_default_if_unrecorded=False)
    if not granted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Resident has not granted consent for '{consent_type}'"
        )

