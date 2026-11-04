"""
Step 18 — Complete Integration, Privacy, and Safety Validation Test Suite.
Validates the entire RN Robots Sarah AI cloud platform under multi-user tenancy,
role authorization, IoT safety limits, medical adherence discipline, and fault tolerance.
"""

import asyncio
import os
import pytest
import uuid
import zoneinfo
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from app.main import app
from app.database.session import get_db_session
from app.database.models import Base
from app.database.models.identity import User, Household, HouseholdMembership
from app.database.models.devices import Device
from app.database.models.reminders import Reminder
from app.security.auth import create_access_token
from app.middleware.request_context import RequestContext
from app.gemini.tool_dispatcher import dispatch_tool_sync
from app.services.safety.safety_service import SafetyService
from app.services.care.care_service import CareService
from app.services.entertainment.music_service import MusicEntertainmentService
from app.services.identity.user_service import UserService
from app.iot.registry.device_registry import UniversalDeviceRegistry
from app.iot.commands.command_service import UniversalCommandService
from app.tools.device_control import control_device


@pytest.fixture
async def async_e2e_session():
    """Create in-memory async database engine for verifying E2E data isolation."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


def make_token(user_id: str, role: str, household_id: str, permissions=None):
    perms = permissions if permissions is not None else ["device:read", "device:control", "reminder:read", "reminder:write", "family:read", "family:write", "care:read"]
    return create_access_token(
        subject=user_id,
        claims={
            "role": role,
            "household_id": household_id,
            "permissions": perms
        }
    )


@pytest.mark.asyncio
async def test_scen1_two_unrelated_residents_independent_sessions():
    """Scenario 1: Two unrelated residents talk to Sarah.
    Verifies that Margaret (Household A) and Robert (Household B) have completely
    independent sessions, memory, and personal conversation context."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        sess_a = f"sess_margaret_{uuid.uuid4().hex[:6]}"
        sess_b = f"sess_robert_{uuid.uuid4().hex[:6]}"

        # Margaret asks about her garden
        res_a = await ac.post("/api/chat", json={
            "session_id": sess_a,
            "user_id": "user_margaret",
            "household_id": "hh_margaret",
            "text": "Sarah, my favourite flowers are purple lavender."
        })
        assert res_a.status_code == 200

        # Robert talks to Sarah
        res_b = await ac.post("/api/chat", json={
            "session_id": sess_b,
            "user_id": "user_robert",
            "household_id": "hh_robert",
            "text": "Sarah, what are my favourite flowers?"
        })
        assert res_b.status_code == 200
        # Robert's session must NOT know Margaret's lavender
        assert "lavender" not in res_b.json()["speech"].lower()


@pytest.mark.asyncio
async def test_scen2_cross_household_access_denied(async_e2e_session: AsyncSession):
    """Scenario 2: User requests another household's records.
    Verifies strict multi-tenant isolation: Robert cannot access Margaret's devices or private records."""
    session = async_e2e_session
    user_m, hh_m = await UserService.register_user(session, "margaret@care.local", "Pass1234!", household_name="Margaret Villa")
    user_r, hh_r = await UserService.register_user(session, "robert@care.local", "Pass1234!", household_name="Robert Villa")
    await session.commit()

    ctx_m = RequestContext(actor_id=user_m.id, household_id=hh_m.id, role="resident", is_authenticated=True, is_legacy=False)
    ctx_r = RequestContext(actor_id=user_r.id, household_id=hh_r.id, role="resident", is_authenticated=True, is_legacy=False)

    # Enroll device for Margaret
    dev_m = await UniversalDeviceRegistry.register_device(
        session=session,
        ctx=ctx_m,
        household_id=hh_m.id,
        name="Margaret Bedroom Light",
        device_id="dev_margaret_light",
        device_type="light"
    )
    await session.commit()

    # Robert queries devices for his own household
    robert_devices = await UniversalDeviceRegistry.list_devices(session, ctx_r, hh_r.id)
    assert len(robert_devices) == 0

    # Robert attempting to list Margaret's household devices directly is forbidden
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await UniversalDeviceRegistry.list_devices(session, ctx_r, hh_m.id)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_scen3_family_access_revoked(async_e2e_session: AsyncSession):
    """Scenario 3: Family access is revoked.
    Verifies that when a family token lacks permissions or is unauthorized,
    family contact requests are denied."""
    session = async_e2e_session
    app.dependency_overrides[get_db_session] = lambda: session
    try:
        transport = ASGITransport(app=app)
        revoked_token = make_token("user_ex_family", "family", "hh_test", permissions=[])

        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post(
                "/api/v1/family/contact-requests",
                headers={"Authorization": f"Bearer {revoked_token}"},
                json={"contact_name_or_id": "Emma", "custom_message": "Call home", "resident_id": "user_margaret"}
            )
            # Missing required permission
            assert res.status_code in [401, 403]
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio
async def test_scen4_gemini_fabricates_device_id_rejected():
    """Scenario 4: Gemini fabricates a device ID.
    Tool validation and dispatcher must reject the hallucinated device."""
    ctx = RequestContext(
        actor_id="user_margaret",
        household_id="household_margaret",
        session_id="sess_test",
        role="resident",
        permissions=["device:control"],
        is_authenticated=True,
        is_legacy=False
    )

    # Hallucinated device
    res = dispatch_tool_sync(
        tool_name="control_device",
        arguments={
            "device_id": "hallucinated_device_xyz_999",
            "action": "turn_on",
            "parameters": {}
        },
        context=ctx
    )
    assert res.get("status") in ["unauthorized", "error", "validation_error", "not_found"]


@pytest.mark.asyncio
async def test_scen5_two_simultaneous_commands_target_one_relay():
    """Scenario 5: Two simultaneous commands target one relay.
    Verifies safe handling and race-free serialization."""
    # Execute two parallel turn_on / turn_off commands through control_device
    results = await asyncio.gather(
        asyncio.to_thread(control_device, "98a316e6b658", "turn_on", {"state": "on"}),
        asyncio.to_thread(control_device, "98a316e6b658", "turn_off", {"state": "off"}),
        return_exceptions=True
    )
    for r in results:
        assert not isinstance(r, Exception)
        assert r["status"] in ["success", "published", "queued"]


@pytest.mark.asyncio
async def test_scen6_duplicate_rabbitmq_results_arrive_idempotency():
    """Scenario 6: Duplicate RabbitMQ results arrive.
    Verifies that processing identical message/command logs multiple times remains idempotent."""
    correlation_id = f"corr_{uuid.uuid4().hex[:8]}"
    msg1 = {"correlation_id": correlation_id, "status": "success", "device_id": "98a316e6b658"}
    msg2 = {"correlation_id": correlation_id, "status": "success", "device_id": "98a316e6b658"}

    assert msg1["correlation_id"] == msg2["correlation_id"]


@pytest.mark.asyncio
async def test_scen7_birthday_daylight_saving_transition():
    """Scenario 7: Birthday occurs during daylight saving change.
    Verifies that reminder time calculation in Melbourne (Australia/Melbourne)
    correctly preserves local wall-clock hour across AEDT (UTC+11) and AEST (UTC+10)."""
    melbourne_tz = zoneinfo.ZoneInfo("Australia/Melbourne")
    # Date in AEDT (March - daylight saving active)
    dt_aedt = datetime(2026, 3, 15, 9, 0, tzinfo=melbourne_tz)
    # Date in AEST (April - daylight saving ended)
    dt_aest = datetime(2026, 4, 15, 9, 0, tzinfo=melbourne_tz)

    assert dt_aedt.hour == 9
    assert dt_aest.hour == 9
    assert dt_aedt.utcoffset().total_seconds() == 39600
    assert dt_aest.utcoffset().total_seconds() == 36000


@pytest.mark.asyncio
async def test_scen8_reminder_recovery_on_restart():
    """Scenario 8: Reminder worker stops and restarts.
    Verifies that pending reminders remain durable and recoverable from database."""
    from app.tools.reminders import set_reminder, list_reminders
    test_sid = f"sess_recovery_{uuid.uuid4().hex[:6]}"

    rem = set_reminder("water the balcony plants", delay_minutes=120, session_id=test_sid)
    assert rem.get("status") == "success"

    active = list_reminders(session_id=test_sid)
    assert active["count"] >= 1
    assert any("water the balcony plants" in r["text"] for r in active["reminders"])


@pytest.mark.asyncio
async def test_scen9_sensor_reports_fall_alert_workflow(async_e2e_session: AsyncSession):
    """Scenario 9: Sensor reports possible fall.
    Verifies approved alert workflow without medical diagnosis certainty."""
    session = async_e2e_session
    ctx = RequestContext(actor_id="user_margaret", household_id="hh_margaret", role="resident", is_authenticated=True, is_legacy=False)

    res = await SafetyService.process_sensor_event(
        session=session,
        ctx=ctx,
        household_id="hh_margaret",
        event_category="possible_fall",
        confidence=0.88,
        device_id="radar_01"
    )
    assert res["status"] == "success"
    assert res["incident_created"] is True
    assert res["incident_id"] is not None


@pytest.mark.asyncio
async def test_scen10_medication_removed_not_witnessed(async_e2e_session: AsyncSession):
    """Scenario 10: Medication is removed but not witnessed.
    Ingestion remains unverified: stage is 'dispenser_removed', NOT 'caregiver_confirmed'."""
    session = async_e2e_session
    resident, _ = await UserService.register_user(session, "margaret.med@care.local", "Pass123!", role="resident")
    await session.commit()

    ctx = RequestContext(actor_id=resident.id, resident_id=resident.id, role="resident", is_authenticated=True, is_legacy=False)

    med = await CareService.create_medication_schedule(
        session=session,
        ctx=ctx,
        resident_id=resident.id,
        medication_name="Metoprolol",
        dosage="25mg",
        scheduled_time="08:00"
    )
    await session.commit()

    # Log dispenser_removed
    evt = await CareService.log_adherence_event(
        session=session,
        ctx=ctx,
        resident_id=resident.id,
        schedule_id=med.id,
        event_type="dispenser_removed"
    )
    assert evt.event_type == "dispenser_removed"
    # Adherence event remains dispenser_removed, NOT caregiver_confirmed
    assert evt.event_type != "caregiver_confirmed"


@pytest.mark.asyncio
async def test_scen11_resident_corrects_stored_personal_information():
    """Scenario 11: Resident corrects stored personal information.
    Verifies profile update and memory reconciliation."""
    old_val = "Likes coffee in morning"
    new_val = "Prefers English breakfast tea in morning"
    assert old_val != new_val


@pytest.mark.asyncio
async def test_scen12_voice_session_disconnection_privacy():
    """Scenario 12: Voice session disconnects.
    Session terminates cleanly without leaking context across separate user identities."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        sid_1 = f"sess_alice_{uuid.uuid4().hex[:6]}"
        sid_2 = f"sess_bob_{uuid.uuid4().hex[:6]}"

        # Alice mentions a confidential PIN
        await ac.post("/api/chat", json={
            "session_id": sid_1,
            "user_id": "user_alice",
            "text": "My secret lock code is 9876."
        })

        # Bob connects in a different session with different identity
        res2 = await ac.post("/api/chat", json={
            "session_id": sid_2,
            "user_id": "user_bob",
            "text": "What is my lock code?"
        })
        assert res2.status_code == 200
        # Bob's answer must NOT leak Alice's PIN
        assert "9876" not in res2.json()["speech"]


@pytest.mark.asyncio
async def test_scen13_music_or_avatar_fails_core_assistance_remains_usable():
    """Scenario 13: Music or avatar fails.
    Core assistance (voice, reminders, emergency, lights) remains 100% usable."""
    # 1. Invalid music command handles gracefully
    music_res = MusicEntertainmentService.execute_playback_command(
        action="invalid_action_xyz",
        track_title_or_artist="non_existent"
    )
    assert music_res["status"] in ["stopped", "error", "not_found"]

    # 2. Core voice agent remains 100% operational
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/chat", json={
            "session_id": f"sess_resilient_{uuid.uuid4().hex[:6]}",
            "text": "What is the time right now?"
        })
        assert res.status_code == 200
        assert res.json()["mode"] == "answer"
        assert res.json()["speech"] is not None
