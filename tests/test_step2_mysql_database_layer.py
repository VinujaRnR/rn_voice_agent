"""Tests for Step 2: Asynchronous database layer, SQLAlchemy models, encryption, and repositories."""
import os
import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, text
from alembic import command
from alembic.config import Config

from app.database.models import (
    Base,
    User,
    Household,
    HouseholdMembership,
    ResidentProfile,
    AccessGrant,
    ConsentRecord,
    Representative,
    Session,
    ConversationMessage,
    PendingAction,
    UserPreference,
    PersonalMemory,
    Device,
    DeviceCapability,
    Gateway,
    DeviceBinding,
    Reminder,
    RecurrenceRule,
    ReminderOccurrence
)
from app.database.repositories import (
    UserRepository,
    ConversationRepository,
    DeviceRepository,
    ReminderRepository,
    AuthRepository
)
from app.database.encryption import field_encryptor


@pytest.fixture
async def async_test_session():
    """Create in-memory async database engine, initialize schema, and yield session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_all_tables_metadata():
    """Verify all 19 domain tables exist in Base.metadata with expected table names."""
    expected_tables = {
        "users", "households", "household_memberships", "resident_profiles",
        "access_grants", "consent_records", "representatives",
        "sessions", "conversation_messages", "pending_actions",
        "user_preferences", "personal_memories",
        "devices", "device_capabilities", "gateways", "device_bindings",
        "reminders", "recurrence_rules", "reminder_occurrences"
    }
    actual_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(actual_tables)
    assert len(actual_tables) >= 19


@pytest.mark.asyncio
async def test_field_encryption_and_decryption(async_test_session: AsyncSession):
    """Verify transparent field-level AES encryption and decryption on storage/retrieval."""
    raw_secret_medical = "Patient requires insulin at 08:00 AM and blood pressure checks."
    raw_secret_phone = "+61412345678"

    # Test standalone encryptor
    enc_token = field_encryptor.encrypt(raw_secret_medical)
    assert enc_token != raw_secret_medical
    decrypted = field_encryptor.decrypt(enc_token)
    assert decrypted == raw_secret_medical

    # Test database model transparent encryption
    user_repo = UserRepository(async_test_session)
    user = await user_repo.create_user(email="test.resident@rnrobots.com", full_name="Robert Brown", role="resident")
    profile = await user_repo.upsert_resident_profile(
        user_id=user.id,
        medical_notes=raw_secret_medical,
        emergency_contact_phone=raw_secret_phone
    )
    await async_test_session.commit()

    # Query directly with SQL raw text to verify data is stored encrypted in column
    res = await async_test_session.execute(
        text(f"SELECT medical_notes, emergency_contact_phone FROM resident_profiles WHERE id = '{profile.id}'")
    )
    raw_row = res.fetchone()
    stored_medical, stored_phone = raw_row[0], raw_row[1]
    assert stored_medical != raw_secret_medical
    assert stored_phone != raw_secret_phone

    # Query through SQLAlchemy model to verify automatic decryption
    fetched_profile = await user_repo.get_resident_profile(user.id)
    assert fetched_profile.medical_notes == raw_secret_medical
    assert fetched_profile.emergency_contact_phone == raw_secret_phone


@pytest.mark.asyncio
async def test_conversation_cryptographic_chaining(async_test_session: AsyncSession):
    """Verify conversation message chaining with SHA-256 hashes and sequence numbers."""
    conv_repo = ConversationRepository(async_test_session)
    session_id = "test_chain_session_1"
    sess = await conv_repo.get_or_create_session(session_id=session_id)
    assert sess.is_active is True

    # Message 1
    m1 = await conv_repo.add_message(session_id=session_id, sender="user", content="Hello Sarah")
    assert m1.seq_num == 1
    assert m1.prev_hash is None
    assert len(m1.content_hash) == 64

    # Message 2
    m2 = await conv_repo.add_message(session_id=session_id, sender="assistant", content="Hello! How can I help?")
    assert m2.seq_num == 2
    assert m2.prev_hash == m1.content_hash
    assert len(m2.content_hash) == 64

    # Message 3
    m3 = await conv_repo.add_message(session_id=session_id, sender="user", content="Turn on the lights")
    assert m3.seq_num == 3
    assert m3.prev_hash == m2.content_hash

    # Fetch ordered messages
    messages = await conv_repo.get_messages(session_id=session_id)
    assert len(messages) == 3
    assert messages[0].content == "Hello Sarah"
    assert messages[2].content == "Turn on the lights"


@pytest.mark.asyncio
async def test_pending_action_lifecycle(async_test_session: AsyncSession):
    """Verify multi-turn pending action saving, retrieval, and resolution."""
    conv_repo = ConversationRepository(async_test_session)
    session_id = "test_pending_session"
    await conv_repo.get_or_create_session(session_id=session_id)

    pending = await conv_repo.save_pending_action(
        session_id=session_id,
        action="set_power",
        parameters={"state": "on"},
        missing_fields=["device_id"]
    )
    assert pending.status == "pending"

    fetched = await conv_repo.get_pending_action(session_id=session_id)
    assert fetched is not None
    assert fetched.action == "set_power"
    assert fetched.missing_fields == ["device_id"]

    resolved = await conv_repo.resolve_pending_action(session_id=session_id)
    assert resolved is True

    # No more pending actions
    fetched_after = await conv_repo.get_pending_action(session_id=session_id)
    assert fetched_after is None


@pytest.mark.asyncio
async def test_device_repository_and_capabilities(async_test_session: AsyncSession):
    """Verify device registration, capabilities, and gateway bindings."""
    dev_repo = DeviceRepository(async_test_session)
    user_repo = UserRepository(async_test_session)

    household = await user_repo.create_household(name="Brisbane Care Facility")
    gateway = await dev_repo.register_gateway(
        household_id=household.id,
        gateway_identifier="hub-01",
        gateway_name="Primary Rn Hub",
        mac_address="34:17:eb:c3:b4:79"
    )
    assert gateway.gateway_identifier == "hub-01"

    dev = await dev_repo.register_device(
        name="Living Room Glow Light",
        device_id="light_glow_1",
        type="light_glow",
        household_id=household.id,
        connection_type="WiFi"
    )
    assert dev.id == "light_glow_1"

    await dev_repo.add_capability(device_id=dev.id, action_name="LIGHT_ON")
    await dev_repo.add_capability(device_id=dev.id, action_name="LIGHT_OFF")
    caps = await dev_repo.get_capabilities(device_id=dev.id)
    assert len(caps) == 2

    binding = await dev_repo.bind_device(
        device_id=dev.id,
        gateway_id=gateway.id,
        channel_key="relay:light_glow"
    )
    assert binding.channel_key == "relay:light_glow"

    # Test power state toggle
    await dev_repo.update_power_state(device_id=dev.id, power_state="on")
    updated_dev = await dev_repo.get_by_hardware_id("light_glow_1")
    assert updated_dev.power_state == "on"


@pytest.mark.asyncio
async def test_reminders_and_recurrence_rules(async_test_session: AsyncSession):
    """Verify care reminders, recurrence rules, and occurrence tracking."""
    rem_repo = ReminderRepository(async_test_session)
    user_repo = UserRepository(async_test_session)

    user = await user_repo.create_user(email="care.resident@rnrobots.com", full_name="Alice Wang")
    now_utc = datetime.now(timezone.utc)

    reminder = await rem_repo.create_reminder(
        text="Take morning medication",
        due_at_utc=now_utc,
        delay_seconds=600,
        user_id=user.id,
        recurrence="daily"
    )
    assert reminder.id.startswith("rem_")
    assert reminder.recurrence == "daily"

    rule = await rem_repo.add_recurrence_rule(
        reminder_id=reminder.id,
        frequency="daily",
        interval=1,
        by_days=["monday", "wednesday", "friday"]
    )
    assert rule.frequency == "daily"
    assert rule.by_days == ["monday", "wednesday", "friday"]

    occ = await rem_repo.record_occurrence(
        reminder_id=reminder.id,
        scheduled_time=now_utc,
        status="pending"
    )
    assert occ.status == "pending"

    active = await rem_repo.get_active_reminders(user_id=user.id)
    assert len(active) == 1

    cancelled = await rem_repo.cancel_reminder(reminder.id)
    assert cancelled is True
    active_after = await rem_repo.get_active_reminders(user_id=user.id)
    assert len(active_after) == 0


@pytest.mark.asyncio
async def test_authorization_grants_and_consent(async_test_session: AsyncSession):
    """Verify access grants, permission scopes, consent logging, and representatives."""
    user_repo = UserRepository(async_test_session)
    auth_repo = AuthRepository(async_test_session)

    resident = await user_repo.create_user(email="resident@rnrobots.com", role="resident")
    carer = await user_repo.create_user(email="carer@rnrobots.com", role="caregiver")
    family = await user_repo.create_user(email="daughter@rnrobots.com", role="family")

    # Access grant
    grant = await auth_repo.grant_access(
        granter_id=resident.id,
        grantee_id=carer.id,
        scope="manage_reminders"
    )
    has_rem_access = await auth_repo.check_access(granter_id=resident.id, grantee_id=carer.id, scope="manage_reminders")
    assert has_rem_access is True

    has_dev_access = await auth_repo.check_access(granter_id=resident.id, grantee_id=carer.id, scope="control_devices")
    assert has_dev_access is False

    # Revoke grant
    await auth_repo.revoke_access(grant.id)
    has_rem_access_revoked = await auth_repo.check_access(granter_id=resident.id, grantee_id=carer.id, scope="manage_reminders")
    assert has_rem_access_revoked is False

    # Consent record
    await auth_repo.record_consent(user_id=resident.id, consent_type="voice_recording", is_granted=True)
    assert await auth_repo.check_consent(user_id=resident.id, consent_type="voice_recording") is True
    assert await auth_repo.check_consent(user_id=resident.id, consent_type="camera_feed") is False

    # Representative
    rep = await auth_repo.add_representative(
        resident_id=resident.id,
        representative_id=family.id,
        relationship_type="next_of_kin",
        verified=True
    )
    assert rep.verified is True


@pytest.mark.asyncio
async def test_foreign_key_cascades(async_test_session: AsyncSession):
    """Verify CASCADE deletions when deleting a parent user account."""
    user_repo = UserRepository(async_test_session)
    user = await user_repo.create_user(email="delete_me@rnrobots.com", full_name="Temporary User")
    household = await user_repo.create_household(name="Temp Home")
    await user_repo.add_household_member(household_id=household.id, user_id=user.id)
    await user_repo.upsert_resident_profile(user_id=user.id, preferred_name="Temp")

    # Delete user
    await user_repo.delete(user)
    await async_test_session.commit()

    # Verify profile and membership are cascade deleted
    prof = await user_repo.get_resident_profile(user.id)
    assert prof is None

    res = await async_test_session.execute(
        select(HouseholdMembership).where(HouseholdMembership.user_id == user.id)
    )
    assert res.scalars().first() is None


def test_alembic_schema_migrations():
    """Verify Alembic can apply forward and backward migrations cleanly."""
    test_db = "temp_step2_test.db"
    try:
        if os.path.exists(test_db):
            os.remove(test_db)
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{test_db}")

        # Upgrade head
        command.upgrade(alembic_cfg, "head")

        # Downgrade base
        command.downgrade(alembic_cfg, "base")

    finally:
        if os.path.exists(test_db):
            os.remove(test_db)

