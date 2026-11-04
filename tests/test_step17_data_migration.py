import os
import pytest
import sqlite3
import json
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from app.database.models import Base
from app.database.models.identity import User, Household, HouseholdMembership
from app.database.models.devices import Device
from app.database.models.reminders import Reminder
from app.database.models.conversation import Session as DbSession, ConversationMessage
from app.database.migrations.sqlite_to_mysql_migrator import SQLiteToMySQLMigrator


@pytest.fixture
async def async_migration_session():
    """Create in-memory async database engine for verifying migration logic."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def sample_sqlite_and_json(tmp_path):
    """Create sample SQLite database and devices.json with valid and quarantine records."""
    db_file = str(tmp_path / "test_legacy.db")
    json_file = str(tmp_path / "test_devices.json")

    # 1. Populate SQLite
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            is_awake INTEGER,
            last_active_at TIMESTAMP
        );
    """)
    cur.execute("""
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMP,
            content_hash TEXT,
            turn_hash TEXT,
            user_hash TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE reminders (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            text TEXT,
            due_at_timestamp REAL,
            due_at_iso TEXT,
            delay_seconds INTEGER,
            status TEXT,
            created_at TIMESTAMP,
            reminded_at TIMESTAMP,
            recurrence TEXT
        );
    """)

    # Insert valid session and message
    cur.execute("INSERT INTO sessions VALUES ('sess_valid_1', 'user_m', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, CURRENT_TIMESTAMP)")
    cur.execute("INSERT INTO messages (session_id, role, content, content_hash) VALUES ('sess_valid_1', 'user', 'Turn on the lights', 'hash_123')")
    cur.execute("INSERT INTO messages (session_id, role, content, content_hash) VALUES ('sess_valid_1', 'assistant', 'Lights turned on', 'hash_456')")

    # Insert valid reminder and quarantined reminder (empty text)
    cur.execute("""
        INSERT INTO reminders VALUES (
            'rem_101', 'sess_valid_1', 'Take evening medication', 1762243200.0, '2026-11-04T18:00:00Z',
            3600, 'pending', CURRENT_TIMESTAMP, NULL, 'daily'
        )
    """)
    cur.execute("""
        INSERT INTO reminders VALUES (
            'rem_bad_orphan', 'sess_orphan', '', 1762243200.0, '2026-11-04T18:00:00Z',
            0, 'pending', CURRENT_TIMESTAMP, NULL, 'once'
        )
    """)
    conn.commit()
    conn.close()

    # 2. Populate JSON devices
    devices_data = [
        {
            "id": "dev_farm_light",
            "name": "Testing Farm Light",
            "type": "light",
            "device_id": "98a316e6b658",
            "protocol": "rabbitmq",
            "capabilities": ["power", "telemetry"],
            "status": "online"
        },
        {
            "id": "dev_radar_sensor",
            "name": "Living Room Radar",
            "type": "radar_sensor",
            "device_id": "98a316e6b699",
            "protocol": "matter",
            "capabilities": ["presence", "fall_detection"],
            "status": "online"
        }
    ]
    with open(json_file, "w") as f:
        json.dump(devices_data, f)

    return db_file, json_file


@pytest.mark.asyncio
async def test_migration_inventory(sample_sqlite_and_json):
    """Verify inventory reads SQLite row counts and JSON records accurately."""
    db_file, json_file = sample_sqlite_and_json
    migrator = SQLiteToMySQLMigrator(sqlite_db_path=db_file, json_devices_path=json_file)
    inv = migrator.inventory()

    assert inv["sqlite_tables"]["sessions"] == 1
    assert inv["sqlite_tables"]["messages"] == 2
    assert inv["sqlite_tables"]["reminders"] == 2
    assert inv["json_devices_count"] == 2


@pytest.mark.asyncio
async def test_migration_dry_run(sample_sqlite_and_json, async_migration_session):
    """Verify dry-run performs schema mapping and checks without persisting rows."""
    db_file, json_file = sample_sqlite_and_json
    migrator = SQLiteToMySQLMigrator(
        sqlite_db_path=db_file,
        json_devices_path=json_file,
        dry_run=True,
        session=async_migration_session
    )

    report = await migrator.run_migration()
    report_dict = report.to_dict()

    assert report_dict["is_dry_run"] is True
    assert report_dict["migrated"]["devices"] == 2
    assert report_dict["migrated"]["reminders"] == 1
    assert report_dict["quarantined"]["reminders"] == 1
    assert report_dict["errors_count"] == 0

    # Since it was dry-run, DB tables must be empty
    q_devs = await async_migration_session.execute(select(Device))
    assert len(q_devs.scalars().all()) == 0


@pytest.mark.asyncio
async def test_migration_execution_and_integrity(sample_sqlite_and_json, async_migration_session):
    """Verify full migration imports devices, sessions, messages, and reminders with verified foreign keys."""
    db_file, json_file = sample_sqlite_and_json
    migrator = SQLiteToMySQLMigrator(
        sqlite_db_path=db_file,
        json_devices_path=json_file,
        dry_run=False,
        session=async_migration_session
    )

    report = await migrator.run_migration()
    assert report.migrated["devices"] == 2
    assert report.migrated["sessions"] == 1
    assert report.migrated["messages"] == 2
    assert report.migrated["reminders"] == 1
    assert report.quarantined["reminders"] == 1

    # Verify foreign-key relations in destination database
    q_household = await async_migration_session.execute(select(Household))
    household = q_household.scalar_one_or_none()
    assert household is not None
    assert household.name == "Legacy Migrated Household"

    # Verify devices
    q_devs = await async_migration_session.execute(select(Device))
    devs = q_devs.scalars().all()
    assert len(devs) == 2
    assert any(d.device_id == "98a316e6b658" for d in devs)

    # Verify reminders
    q_rems = await async_migration_session.execute(select(Reminder))
    rems = q_rems.scalars().all()
    assert len(rems) == 1
    rem = rems[0]
    assert rem.id == "rem_101"
    assert rem.text == "Take evening medication"
    assert rem.recurrence == "daily"
    assert rem.due_at_utc is not None

    # Verify conversation messages
    q_msgs = await async_migration_session.execute(select(ConversationMessage))
    msgs = q_msgs.scalars().all()
    assert len(msgs) == 2
    assert msgs[0].sender == "user"
    assert msgs[0].content == "Turn on the lights"
    assert msgs[1].sender == "assistant"
    assert msgs[1].prev_hash == msgs[0].content_hash
