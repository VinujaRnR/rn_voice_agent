"""Resident care profiles, personal preferences, memories, and access management API."""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db_session, transaction
from app.database.repositories.auth_repository import AuthRepository
from app.middleware.request_context import RequestContext, get_request_context
from app.middleware.authorization import require_authenticated
from app.middleware.tenant_isolation import enforce_resident_access
from app.services.personalization.profile_service import PersonalizationProfileService
from app.services.personalization.preference_service import PersonalizationPreferenceService
from app.services.personalization.memory_service import PersonalizationMemoryService
from app.services.personalization.context_service import PersonalizationContextService
from app.schemas.profiles import (
    ResidentProfileResponse,
    ResidentProfileUpdateRequest,
    ResidentPreferenceResponse,
    ResidentPreferenceUpdateRequest,
    MemoryCreateRequest,
    MemoryResponse,
    AccessGrantCreateRequest,
    AccessGrantResponse,
    ConsentRecordRequest
)

router = APIRouter(prefix="/api/v1/residents", tags=["Resident Care Profiles"])


@router.get("/{resident_id}", response_model=ResidentProfileResponse)
async def get_resident_profile(
    resident_id: str,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    """Retrieve resident profile with decrypted attributes according to authorization & consent."""
    profile = await PersonalizationProfileService.get_authorized_profile(
        session=session,
        ctx=ctx,
        target_resident_id=resident_id
    )
    return ResidentProfileResponse(**profile)


@router.put("/{resident_id}", response_model=ResidentProfileResponse)
async def update_resident_profile(
    resident_id: str,
    payload: ResidentProfileUpdateRequest,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    """Update resident profile attributes."""
    async with transaction(session):
        updated = await PersonalizationProfileService.update_authorized_profile(
            session=session,
            ctx=ctx,
            target_resident_id=resident_id,
            preferred_name=payload.preferred_name,
            birth_year=payload.birth_year,
            medical_notes=payload.medical_notes,
            emergency_contact_phone=payload.emergency_contact_phone,
            primary_language=payload.primary_language
        )
    return ResidentProfileResponse(**updated)


@router.get("/{resident_id}/preferences", response_model=ResidentPreferenceResponse)
async def get_preferences(
    resident_id: str,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    """Retrieve resident voice persona, speech rate, and display preferences."""
    pref = await PersonalizationPreferenceService.get_resident_preferences(
        session=session,
        ctx=ctx,
        target_resident_id=resident_id
    )
    return ResidentPreferenceResponse(**pref)


@router.put("/{resident_id}/preferences", response_model=ResidentPreferenceResponse)
async def update_preferences(
    resident_id: str,
    payload: ResidentPreferenceUpdateRequest,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    """Update resident preferences."""
    async with transaction(session):
        updated = await PersonalizationPreferenceService.update_resident_preferences(
            session=session,
            ctx=ctx,
            target_resident_id=resident_id,
            wake_word=payload.wake_word,
            voice_name=payload.voice_name,
            speaking_rate=payload.speaking_rate,
            volume=payload.volume,
            temperature_unit=payload.temperature_unit
        )
    return ResidentPreferenceResponse(**updated)


@router.get("/{resident_id}/memories", response_model=List[MemoryResponse])
async def list_memories(
    resident_id: str,
    category: Optional[str] = Query(None, description="Optional category filter"),
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    """Retrieve decrypted personal memories for the resident."""
    memories = await PersonalizationMemoryService.get_authorized_memories(
        session=session,
        ctx=ctx,
        target_resident_id=resident_id,
        category=category
    )
    return [MemoryResponse(**m) for m in memories]


@router.post("/{resident_id}/memories", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    resident_id: str,
    payload: MemoryCreateRequest,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    """Add a new encrypted personal memory for the resident."""
    async with transaction(session):
        saved = await PersonalizationMemoryService.save_personal_memory(
            session=session,
            ctx=ctx,
            target_resident_id=resident_id,
            memory_key=payload.memory_key,
            memory_value=payload.memory_value,
            category=payload.category,
            importance_score=payload.importance_score
        )
    return MemoryResponse(**saved)


@router.get("/{resident_id}/context")
async def get_resident_context(
    resident_id: str,
    ctx: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session)
):
    """Return consolidated contextual profile for Sarah conversational reasoning."""
    context = await PersonalizationContextService.get_authorized_context(
        session=session,
        ctx=ctx,
        target_resident_id=resident_id
    )
    return {"status": "success", "context": context}


@router.post("/{resident_id}/access", response_model=AccessGrantResponse, status_code=status.HTTP_201_CREATED)
async def grant_resident_access(
    resident_id: str,
    payload: AccessGrantCreateRequest,
    ctx: RequestContext = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session)
):
    """Resident grants explicit scoped access to a caregiver or family member."""
    # Only the resident or admin can grant access on behalf of resident
    if ctx.actor_id != resident_id and ctx.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the resident can grant access to their personal records"
        )

    auth_repo = AuthRepository(session)
    async with transaction(session):
        grant = await auth_repo.grant_access(
            granter_id=resident_id,
            grantee_id=payload.grantee_id,
            scope=payload.scope,
            expires_at=payload.expires_at
        )

    return AccessGrantResponse(
        id=grant.id,
        granter_id=grant.granter_id,
        grantee_id=grant.grantee_id,
        scope=grant.scope,
        status=grant.status,
        expires_at=grant.expires_at.isoformat() if grant.expires_at else None
    )


@router.post("/{resident_id}/consent")
async def update_resident_consent(
    resident_id: str,
    payload: ConsentRecordRequest,
    ctx: RequestContext = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session)
):
    """Record resident's explicit consent or revocation for sensitive care data."""
    if ctx.actor_id != resident_id and ctx.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the resident can record or revoke consent"
        )

    auth_repo = AuthRepository(session)
    async with transaction(session):
        record = await auth_repo.record_consent(
            user_id=resident_id,
            consent_type=payload.consent_type,
            is_granted=payload.is_granted
        )

    return {
        "status": "success",
        "consent_id": record.id,
        "consent_type": record.consent_type,
        "is_granted": record.is_granted,
        "granted_at": record.granted_at.isoformat()
    }

