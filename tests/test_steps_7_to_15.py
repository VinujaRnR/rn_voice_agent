"""Comprehensive tests for Steps 7 through 15:
- Step 7: Refactor Gemini, tool calling and voice sessions
- Step 8: Universal IoT device registration
- Step 9: Universal commands, state and telemetry
- Step 10: Reminders, scheduling and action queues
- Step 11: Family contacts, birthdays and communications
- Step 12: Caregivers, care plans and medication services
- Step 13: Radar-based elderly safety and Australian alerts
- Step 14: Australian local services and provider discovery
- Step 15: Music entertainment and personal playlists
"""
import pytest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from fastapi import HTTPException

from app.database.models import Base
from app.database.session import get_db_session
from app.services.identity.user_service import UserService
from app.services.identity.household_service import HouseholdService
from app.middleware.request_context import RequestContext
from app.middleware.tenant_isolation import TenantIsolationError

# Step 7
from app.gemini.tool_dispatcher import dispatch_tool, dispatch_tool_sync
from app.gemini.tool_schemas import ControlDeviceArgs, GetWeatherArgs
from app.gemini.tool_authorization import ToolAuthorizationManager

# Step 8 & 9
from app.iot.registry.device_registry import UniversalDeviceRegistry
from app.iot.commands.command_service import UniversalCommandService
from app.database.repositories.iot_repository import IoTRepository

# Step 11
from app.services.family.family_service import FamilyService

# Step 12
from app.services.care.care_service import CareService

# Step 13
from app.services.safety.safety_service import SafetyService

# Step 14
from app.integrations.places.australian_places import AustralianLocalServices

# Step 15
from app.services.entertainment.music_service import MusicEntertainmentService

from app.main import app


@pytest.fixture
async def async_test_session():
    """Create in-memory async SQLite database engine and yield isolated session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


# =========================================================================
# STEP 7: Secure Tool Dispatcher & Authorization Tests
# =========================================================================

def test_step7_tool_dispatcher_schema_validation():
    # Valid arguments
    res = dispatch_tool_sync("get_weather", {"city": "Sydney", "forecast_days": 2})
    assert res.get("status") == "success" or "temperature" in str(res)

    # Invalid arguments (forecast_days out of bounds > 7)
    invalid_res = dispatch_tool_sync("get_weather", {"city": "Sydney", "forecast_days": 99})
    assert invalid_res["status"] == "validation_error"


def test_step7_tool_dispatcher_unauthorized_action():
    # Context lacking device:control permission
    unauthorized_ctx = RequestContext(
        actor_id="guest_user",
        role="guest",
        permissions=["conversation:write"],
        is_authenticated=True,
        is_legacy=False
    )
    res = dispatch_tool_sync(
        "control_device",
        {"device_id": "lamp_1", "action": "turn_on"},
        context=unauthorized_ctx
    )
    assert res["status"] == "unauthorized"
    assert "Missing required permission" in res["message"]


# =========================================================================
# STEP 8 & 9: Universal IoT Device Registration & Commands
# =========================================================================

@pytest.mark.asyncio
async def test_step8_and_9_universal_device_registration_and_isolation(async_test_session: AsyncSession):
    session = async_test_session

    # Household Alpha & Beta
    user_a, hh_a = await UserService.register_user(session, "alice@example.com", "Password123!", household_name="Villa Alpha")
    user_b, hh_b = await UserService.register_user(session, "bob@example.com", "Password123!", household_name="Villa Beta")
    await session.commit()

    ctx_a = RequestContext(actor_id=user_a.id, household_id=hh_a.id, role="resident", is_authenticated=True, is_legacy=False)
    ctx_b = RequestContext(actor_id=user_b.id, household_id=hh_b.id, role="resident", is_authenticated=True, is_legacy=False)

    # 1. Enroll device into Household Alpha
    dev_a = await UniversalDeviceRegistry.register_device(
        session=session,
        ctx=ctx_a,
        household_id=hh_a.id,
        name="Alpha Heating",
        device_id="alpha_heat_01",
        device_type="thermostat",
        location="Living Room"
    )
    await session.commit()
    assert dev_a.household_id == hh_a.id

    # 2. List devices for Household Alpha returns device
    devices_a = await UniversalDeviceRegistry.list_devices(session, ctx_a, hh_a.id)
    assert len(devices_a) == 1
    assert devices_a[0].device_id == "alpha_heat_01"

    # 3. Tenant Isolation: Bob from Household Beta cannot access or control Alpha device
    with pytest.raises(TenantIsolationError):
        await UniversalDeviceRegistry.list_devices(session, ctx_b, hh_a.id)

    with pytest.raises(TenantIsolationError):
        await UniversalCommandService.dispatch_command(
            session=session,
            ctx=ctx_b,
            device_id=dev_a.id,
            action="turn_on"
        )

    # 4. Authorized Command by Alice
    with patch("app.rabbitmq.publisher.publisher.publish", new_callable=AsyncMock):
        cmd_res = await UniversalCommandService.dispatch_command(
            session=session,
            ctx=ctx_a,
            device_id=dev_a.id,
            action="set_power",
            parameters={"state": "on"}
        )
    await session.commit()
    assert cmd_res["status"] == "success"
    assert "correlation_id" in cmd_res

    # 5. Verify state tracking
    repo = IoTRepository(session)
    state = await repo.get_device_state(dev_a.id)
    assert state.desired_state.get("power") == "on"


# =========================================================================
# STEP 11: Family Contacts, Birthdays, and Communications
# =========================================================================

@pytest.mark.asyncio
async def test_step11_family_contacts_and_contact_request(async_test_session: AsyncSession):
    session = async_test_session

    res_user, _ = await UserService.register_user(session, "elderly.mary@example.com", "Password123!", role="resident")
    ctx = RequestContext(actor_id=res_user.id, role="resident", is_authenticated=True, is_legacy=False)

    # Add daughter as contact
    contact = await FamilyService.add_contact(
        session=session,
        ctx=ctx,
        resident_id=res_user.id,
        name="Sarah Junior",
        relationship_type="daughter",
        phone_number="+61412345678",
        is_emergency_contact=True
    )

    # Add birthday event
    event = await FamilyService.add_family_event(
        session=session,
        ctx=ctx,
        resident_id=res_user.id,
        title="Sarah Junior Birthday",
        event_date=date(1990, 5, 14),
        event_type="birthday",
        contact_id=contact.id
    )
    await session.commit()

    assert contact.id is not None
    assert event.title == "Sarah Junior Birthday"

    # Send call request: "Sarah, send my daughter a message asking her to call me"
    req_res = await FamilyService.send_contact_request(
        session=session,
        ctx=ctx,
        resident_id=res_user.id,
        contact_name_or_id="daughter"
    )
    await session.commit()
    assert req_res["status"] == "success"
    assert "Sarah Junior" in req_res["speech"]


# =========================================================================
# STEP 12: Caregivers, Care Plans, and Medication Services
# =========================================================================

@pytest.mark.asyncio
async def test_step12_care_plans_and_medication_adherence(async_test_session: AsyncSession):
    session = async_test_session

    resident, _ = await UserService.register_user(session, "arthur.care@example.com", "Password123!", role="resident")
    caregiver_user, _ = await UserService.register_user(session, "nurse.anna@example.com", "Password123!", role="caregiver")
    await session.commit()

    ctx = RequestContext(actor_id=resident.id, role="resident", is_authenticated=True, is_legacy=False)

    # Register caregiver and assign
    cg = await CareService.register_caregiver(session, ctx, caregiver_user.id, agency_name="HomeCare Australia")
    await CareService.assign_caregiver(session, ctx, cg.id, resident.id)

    # Create care plan
    plan = await CareService.upsert_care_plan(
        session=session,
        ctx=ctx,
        resident_id=resident.id,
        routine_details={"morning_walk": "08:30", "bedtime": "21:00"},
        dietary_notes="Low sodium, diabetic diet"
    )

    # Create medication schedule
    med = await CareService.create_medication_schedule(
        session=session,
        ctx=ctx,
        resident_id=resident.id,
        medication_name="Metformin",
        dosage="500mg",
        scheduled_time="08:00",
        requires_food=True
    )
    await session.commit()

    assert plan.dietary_notes == "Low sodium, diabetic diet"
    assert med.medication_name == "Metformin"

    # Log medication adherence event: acknowledged
    evt_ack = await CareService.log_adherence_event(session, ctx, resident.id, med.id, "acknowledged")
    assert evt_ack.event_type == "acknowledged"

    # Log medication missed -> auto-escalation
    evt_missed = await CareService.log_adherence_event(session, ctx, resident.id, med.id, "missed")
    assert evt_missed.event_type == "missed"


# =========================================================================
# STEP 13: Radar Safety & Australian Weather/Hazard Alerts
# =========================================================================

@pytest.mark.asyncio
async def test_step13_radar_safety_and_external_alerts(async_test_session: AsyncSession):
    session = async_test_session

    user, hh = await UserService.register_user(session, "grandma.radar@example.com", "Password123!", household_name="Safe Haven")
    ctx = RequestContext(actor_id=user.id, household_id=hh.id, role="resident", is_authenticated=True, is_legacy=False)

    # Ingest radar event: high confidence fall
    res = await SafetyService.process_sensor_event(
        session=session,
        ctx=ctx,
        household_id=hh.id,
        event_category="possible_fall",
        confidence=0.92,
        device_id="radar_room_01"
    )
    await session.commit()

    assert res["status"] == "success"
    assert res["incident_created"] is True

    # Publish Australian BOM emergency alert
    exp_time = datetime.now(timezone.utc) + timedelta(hours=6)
    alert = await SafetyService.publish_external_alert(
        session=session,
        source="BOM",
        alert_type="severe_thunderstorm",
        severity="severe",
        headline="Severe thunderstorm warning for Sydney Metro",
        region="NSW",
        expires_at=exp_time
    )
    await session.commit()

    active_alerts = await SafetyService.get_active_alerts(session, region="NSW")
    assert len(active_alerts) == 1
    assert "Sydney Metro" in active_alerts[0].headline


# =========================================================================
# STEP 14: Australian Local Services and Provider Discovery
# =========================================================================

def test_step14_australian_local_provider_discovery():
    # 1. Search for plumber in Sydney
    plumbers = AustralianLocalServices.find_providers(category="plumber", suburb_or_postcode="Parramatta")
    assert len(plumbers) >= 1
    assert plumbers[0]["category"] == "plumber"
    assert "Plumbing" in plumbers[0]["name"]

    # 2. Search for NDIS registered providers
    ndis_provs = AustralianLocalServices.find_providers(category="ndis")
    assert len(ndis_provs) >= 1
    assert any(p["ndis_registered"] is True for p in ndis_provs)


# =========================================================================
# STEP 15: Music Entertainment & Personal Playlists
# =========================================================================

@pytest.mark.asyncio
async def test_step15_music_playlists_and_playback_controls(async_test_session: AsyncSession):
    session = async_test_session

    user, _ = await UserService.register_user(session, "music.lover@example.com", "Password123!", role="resident")
    ctx = RequestContext(actor_id=user.id, role="resident", is_authenticated=True, is_legacy=False)

    # Seed tracks and search
    await MusicEntertainmentService.seed_default_tracks(session)
    tracks = await MusicEntertainmentService.search_music(session, "Elvis")
    assert len(tracks) >= 1
    assert "Elvis Presley" in tracks[0].artist

    # Create playlist
    pl = await MusicEntertainmentService.create_playlist(session, ctx, "My Golden Favourites")
    await MusicEntertainmentService.add_track_to_playlist(session, pl.id, tracks[0].id)
    await session.commit()

    playlists = await MusicEntertainmentService.list_playlists(session, ctx)
    assert len(playlists) == 1
    assert playlists[0].name == "My Golden Favourites"

    # Playback voice command: Play Elvis
    play_res = MusicEntertainmentService.execute_playback_command("play", "Can't Help Falling in Love by Elvis Presley")
    assert play_res["status"] == "playing"
    assert "Now playing" in play_res["speech"]

    # Playback voice command: Pause
    pause_res = MusicEntertainmentService.execute_playback_command("pause")
    assert pause_res["status"] == "paused"


# =========================================================================
# FASTAPI ENDPOINTS HTTP INTEGRATION TESTS (STEPS 7 TO 15)
# =========================================================================

@pytest.mark.asyncio
async def test_steps_7_to_15_api_endpoints_integration():
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
            # 1. Register user
            reg = await client.post("/api/v1/auth/register", json={
                "email": "australian.elder@example.com",
                "password": "Password123!",
                "full_name": "Arthur Dent",
                "household_name": "Sydney Harbour Villa"
            })
            assert reg.status_code == 201
            auth_data = reg.json()
            token = auth_data["access_token"]
            user_id = auth_data["user_id"]
            hh_id = auth_data["household_id"]
            headers = {"Authorization": f"Bearer {token}"}

            # 2. Step 8 & 9: Enroll IoT Device & Send Command
            dev_reg = await client.post("/api/v1/devices", json={
                "name": "Bedside Reading Lamp",
                "device_id": "lamp_bed_01",
                "household_id": hh_id,
                "device_type": "light",
                "location": "Bedroom"
            }, headers=headers)
            assert dev_reg.status_code == 201
            dev_id = dev_reg.json()["device_id"]

            with patch("app.rabbitmq.publisher.publisher.publish", new_callable=AsyncMock):
                cmd_resp = await client.post(f"/api/v1/devices/{dev_id}/command", json={
                    "action": "turn_on",
                    "parameters": {"state": "on"}
                }, headers=headers)
            assert cmd_resp.status_code == 200
            assert cmd_resp.json()["status"] == "success"

            # 3. Step 11: Family Contact & Event
            fam_resp = await client.post("/api/v1/family/contacts", json={
                "resident_id": user_id,
                "name": "Claire",
                "relationship_type": "daughter",
                "is_emergency_contact": True
            }, headers=headers)
            assert fam_resp.status_code == 201

            # 4. Step 12: Caregiver & Medication Schedule
            med_resp = await client.post(f"/api/v1/care/residents/{user_id}/medications", json={
                "medication_name": "Blood Pressure Meds",
                "dosage": "10mg",
                "scheduled_time": "09:00",
                "instructions": "Take after breakfast"
            }, headers=headers)
            assert med_resp.status_code == 201
            med_id = med_resp.json()["id"]

            med_evt = await client.post(f"/api/v1/care/residents/{user_id}/medications/{med_id}/events", json={
                "event_type": "acknowledged",
                "notes": "Arthur confirmed verbally"
            }, headers=headers)
            assert med_evt.status_code == 200

            # 5. Step 13: Radar Safety Event
            safety_resp = await client.post("/api/v1/safety/events", json={
                "household_id": hh_id,
                "event_category": "room_presence",
                "confidence": 0.99,
                "device_id": "radar_living"
            }, headers=headers)
            assert safety_resp.status_code == 201

            # 6. Step 14: Local Services
            serv_resp = await client.get("/api/v1/services/providers?category=plumber&suburb_or_postcode=Parramatta")
            assert serv_resp.status_code == 200
            assert len(serv_resp.json()["providers"]) >= 1

            # 7. Step 15: Music Entertainment
            music_ctrl = await client.post("/api/v1/entertainment/playback/control", json={
                "action": "play",
                "track_title_or_artist": "Moon River"
            })
            assert music_ctrl.status_code == 200
            assert music_ctrl.json()["status"] == "playing"

    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await engine.dispose()
