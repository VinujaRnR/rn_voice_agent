"""Tests for Steps 4 & 5: Personalization middleware, encrypted resident care profiles, memories, and access management."""
import pytest
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from fastapi import HTTPException

from app.database.models import Base
from app.database.session import get_db_session
from app.services.identity.user_service import UserService
from app.services.identity.household_service import HouseholdService
from app.services.personalization.profile_service import PersonalizationProfileService
from app.services.personalization.preference_service import PersonalizationPreferenceService
from app.services.personalization.memory_service import PersonalizationMemoryService
from app.services.personalization.context_service import PersonalizationContextService
from app.middleware.request_context import RequestContext
from app.database.repositories.auth_repository import AuthRepository
from app.main import app


@pytest.fixture
async def async_test_session():
    """Create in-memory async SQLite engine and yield isolated session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


# =========================================================================
# 1. Personalization Profile & Sensitive Consent Tests
# =========================================================================

@pytest.mark.asyncio
async def test_profile_service_encryption_and_consent_redaction(async_test_session: AsyncSession):
    session = async_test_session

    # 1. Register resident and create household
    resident, hh = await UserService.register_user(
        session=session,
        email="grandma.dorothy@example.com",
        password="Password123!",
        full_name="Dorothy Gale",
        role="resident",
        household_name="Emerald Villa"
    )

    # 2. Register family member in same household
    daughter, _ = await UserService.register_user(
        session=session,
        email="daughter.emily@example.com",
        password="Password123!",
        full_name="Emily Gale",
        role="family",
        household_id=hh.id
    )

    # 3. Update resident profile with sensitive medical notes
    await PersonalizationProfileService.update_authorized_profile(
        session=session,
        ctx=RequestContext(actor_id=resident.id, household_id=hh.id, role="resident", is_authenticated=True, is_legacy=False),
        target_resident_id=resident.id,
        medical_notes="Type 2 Diabetes, prescribed Metformin 500mg twice daily with meals.",
        emergency_contact_phone="+61400111222"
    )
    await session.commit()

    # Resident reading own profile sees full medical notes
    res_ctx = RequestContext(actor_id=resident.id, household_id=hh.id, role="resident", is_authenticated=True, is_legacy=False)
    own_profile = await PersonalizationProfileService.get_authorized_profile(session, res_ctx, resident.id)
    assert "Metformin 500mg" in own_profile["medical_notes"]
    assert own_profile["emergency_contact_phone"] == "+61400111222"

    # Family member without medical consent gets redacted notes
    fam_ctx = RequestContext(actor_id=daughter.id, household_id=hh.id, role="family", is_authenticated=True, is_legacy=False)
    redacted_profile = await PersonalizationProfileService.get_authorized_profile(session, fam_ctx, resident.id)
    assert redacted_profile["medical_notes"] == "[REDACTED: Consent required]"

    # Resident grants consent for medical data
    auth_repo = AuthRepository(session)
    await auth_repo.record_consent(user_id=resident.id, consent_type="medical_data", is_granted=True)
    await session.commit()

    # Now family member sees medical notes
    consented_profile = await PersonalizationProfileService.get_authorized_profile(session, fam_ctx, resident.id)
    assert "Metformin 500mg" in consented_profile["medical_notes"]


# =========================================================================
# 2. Preferences & Speech Customization Tests
# =========================================================================

@pytest.mark.asyncio
async def test_preference_service(async_test_session: AsyncSession):
    session = async_test_session

    user, _ = await UserService.register_user(
        session=session,
        email="arthur.pendleton@example.com",
        password="Password123!",
        role="resident"
    )
    await session.commit()

    ctx = RequestContext(actor_id=user.id, role="resident", is_authenticated=True, is_legacy=False)

    # Initial default preferences (Sarah persona)
    pref = await PersonalizationPreferenceService.get_resident_preferences(session, ctx, user.id)
    assert pref["wake_word"] == "Sarah"
    assert pref["voice_name"] == "en-US-JennyNeural"
    assert pref["speaking_rate"] == 1.0

    # Update preferences: slower speech rate for elderly clarity, British female voice
    updated = await PersonalizationPreferenceService.update_resident_preferences(
        session=session,
        ctx=ctx,
        target_resident_id=user.id,
        speaking_rate=0.85,
        voice_name="en-GB-SoniaNeural",
        wake_word="Sarah Assistant"
    )
    await session.commit()

    assert updated["speaking_rate"] == 0.85
    assert updated["voice_name"] == "en-GB-SoniaNeural"
    assert updated["wake_word"] == "Sarah Assistant"


# =========================================================================
# 3. Encrypted Personal Memories Tests
# =========================================================================

@pytest.mark.asyncio
async def test_personal_memory_service(async_test_session: AsyncSession):
    session = async_test_session

    user, _ = await UserService.register_user(
        session=session,
        email="grandpa.george@example.com",
        password="Password123!",
        role="resident"
    )
    await session.commit()

    ctx = RequestContext(actor_id=user.id, role="resident", is_authenticated=True, is_legacy=False)

    # Store memories
    await PersonalizationMemoryService.save_personal_memory(
        session=session,
        ctx=ctx,
        target_resident_id=user.id,
        memory_key="granddaughter_name",
        memory_value="Lily, attends university in Sydney",
        category="family",
        importance_score=9
    )
    await PersonalizationMemoryService.save_personal_memory(
        session=session,
        ctx=ctx,
        target_resident_id=user.id,
        memory_key="tea_preference",
        memory_value="Earl Grey with a drop of honey, no milk",
        category="preference",
        importance_score=7
    )
    await session.commit()

    # Retrieve all memories
    memories = await PersonalizationMemoryService.get_authorized_memories(session, ctx, user.id)
    assert len(memories) == 2
    # Verify decrypted content
    keys = {m["memory_key"] for m in memories}
    assert "granddaughter_name" in keys
    assert "tea_preference" in keys

    # Filter by category
    family_mems = await PersonalizationMemoryService.get_authorized_memories(session, ctx, user.id, category="family")
    assert len(family_mems) == 1
    assert family_mems[0]["memory_value"] == "Lily, attends university in Sydney"


# =========================================================================
# 4. Context Service Sarah Aggregation Test
# =========================================================================

@pytest.mark.asyncio
async def test_context_service_aggregation(async_test_session: AsyncSession):
    session = async_test_session

    user, hh = await UserService.register_user(
        session=session,
        email="eleanor.rigby@example.com",
        password="Password123!",
        full_name="Eleanor Rigby",
        role="resident",
        household_name="Abbey Road Retreat"
    )
    ctx = RequestContext(actor_id=user.id, household_id=hh.id, role="resident", is_authenticated=True, is_legacy=False)

    await PersonalizationMemoryService.save_personal_memory(
        session=session,
        ctx=ctx,
        target_resident_id=user.id,
        memory_key="favorite_music",
        memory_value="Classical cello and Beatles acoustic songs",
        category="preference",
        importance_score=8
    )
    await session.commit()

    full_context = await PersonalizationContextService.get_authorized_context(session, ctx, user.id)
    assert full_context["resident_id"] == user.id
    assert full_context["preferred_name"] == "Eleanor Rigby"
    assert full_context["household"]["name"] == "Abbey Road Retreat"
    assert full_context["preferences"]["wake_word"] == "Sarah"
    assert len(full_context["memories"]) == 1
    assert full_context["memories"][0]["memory_key"] == "favorite_music"


# =========================================================================
# 5. Profiles API Endpoints HTTP Integration Tests
# =========================================================================

@pytest.mark.asyncio
async def test_profiles_api_routes():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Register resident account
            reg = await client.post("/api/v1/auth/register", json={
                "email": "william.bell@example.com",
                "password": "Password123!",
                "full_name": "William Bell",
                "role": "resident",
                "household_name": "Bell Manor"
            })
            assert reg.status_code == 201
            auth_data = reg.json()
            token = auth_data["access_token"]
            user_id = auth_data["user_id"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            # 2. Update profile
            put_prof = await client.put(f"/api/v1/residents/{user_id}", json={
                "preferred_name": "Bill",
                "birth_year": 1944,
                "primary_language": "en",
                "medical_notes": "Mild arthritis in hands, needs warm room.",
                "emergency_contact_phone": "+61411222333"
            }, headers=auth_headers)
            assert put_prof.status_code == 200, put_prof.text
            prof_data = put_prof.json()
            assert prof_data["preferred_name"] == "Bill"
            assert prof_data["birth_year"] == 1944

            # 3. Get profile
            get_prof = await client.get(f"/api/v1/residents/{user_id}", headers=auth_headers)
            assert get_prof.status_code == 200
            assert get_prof.json()["preferred_name"] == "Bill"

            # 4. Update and get preferences
            put_pref = await client.put(f"/api/v1/residents/{user_id}/preferences", json={
                "speaking_rate": 0.9,
                "volume": 0.95,
                "temperature_unit": "celsius"
            }, headers=auth_headers)
            assert put_pref.status_code == 200
            assert put_pref.json()["speaking_rate"] == 0.9

            get_pref = await client.get(f"/api/v1/residents/{user_id}/preferences", headers=auth_headers)
            assert get_pref.status_code == 200
            assert get_pref.json()["speaking_rate"] == 0.9

            # 5. Create and list memories
            mem_res = await client.post(f"/api/v1/residents/{user_id}/memories", json={
                "memory_key": "pet_dog",
                "memory_value": "Golden retriever named Buster",
                "category": "family",
                "importance_score": 8
            }, headers=auth_headers)
            assert mem_res.status_code == 201
            assert mem_res.json()["memory_key"] == "pet_dog"

            list_mems = await client.get(f"/api/v1/residents/{user_id}/memories", headers=auth_headers)
            assert list_mems.status_code == 200
            assert len(list_mems.json()) == 1

            # 6. Get Sarah aggregated context
            ctx_res = await client.get(f"/api/v1/residents/{user_id}/context", headers=auth_headers)
            assert ctx_res.status_code == 200
            assert ctx_res.json()["context"]["preferred_name"] == "Bill"

            # 7. Register a caregiver
            caregiver_reg = await client.post("/api/v1/auth/register", json={
                "email": "nurse.jen@example.com",
                "password": "Password123!",
                "full_name": "Jen Nurse",
                "role": "caregiver"
            })
            assert caregiver_reg.status_code == 201
            cg_id = caregiver_reg.json()["user_id"]

            # 8. Grant access to caregiver
            grant_res = await client.post(f"/api/v1/residents/{user_id}/access", json={
                "grantee_id": cg_id,
                "scope": "profile:read"
            }, headers=auth_headers)
            assert grant_res.status_code == 201
            assert grant_res.json()["scope"] == "profile:read"

            # 9. Record consent
            consent_res = await client.post(f"/api/v1/residents/{user_id}/consent", json={
                "consent_type": "voice_recording",
                "is_granted": True
            }, headers=auth_headers)
            assert consent_res.status_code == 200
            assert consent_res.json()["is_granted"] is True

    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await engine.dispose()

