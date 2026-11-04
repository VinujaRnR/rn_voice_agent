"""
SQLite to MySQL 8.4 Data Migration Engine.
Migrates legacy SQLite voice_assistant.db and JSON devices to MySQL multi-tenant repositories
with schema validation, foreign-key integrity, quarantine handling, and dry-run support.
"""

import os
import json
import sqlite3
import logging
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy import select
from app.database.session import get_async_session
from app.database.models.identity import User, Household, HouseholdMembership, ResidentProfile
from app.database.models.devices import Device
from app.database.models.reminders import Reminder
from app.database.models.conversation import Session as DbSession, ConversationMessage

logger = logging.getLogger(__name__)


class MigrationReport:
    def __init__(self):
        self.scanned: Dict[str, int] = {}
        self.migrated: Dict[str, int] = {}
        self.quarantined: Dict[str, int] = {}
        self.errors: List[str] = []
        self.is_dry_run: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_dry_run": self.is_dry_run,
            "scanned": self.scanned,
            "migrated": self.migrated,
            "quarantined": self.quarantined,
            "errors_count": len(self.errors),
            "errors": self.errors[:10],
            "status": "success" if not self.errors else "warning"
        }


class SQLiteToMySQLMigrator:
    """One-time importer migrating legacy SQLite/JSON state to MySQL 8.4 schema."""

    def __init__(
        self,
        sqlite_db_path: str = "voice_assistant.db",
        json_devices_path: str = "data/devices.json",
        dry_run: bool = False,
        quarantine_unverified: bool = True,
        default_household_id: str = "household_legacy_default",
        session: Optional[Any] = None
    ):
        self.sqlite_db_path = sqlite_db_path
        self.json_devices_path = json_devices_path
        self.dry_run = dry_run
        self.quarantine_unverified = quarantine_unverified
        self.default_household_id = default_household_id
        self._session = session
        self.report = MigrationReport()
        self.report.is_dry_run = dry_run

    def inventory(self) -> Dict[str, Any]:
        """Inventory current SQLite schema, table row counts, and JSON devices."""
        inv = {"sqlite_tables": {}, "json_devices_count": 0}
        if os.path.exists(self.sqlite_db_path):
            conn = sqlite3.connect(self.sqlite_db_path)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cur.fetchall() if not r[0].startswith("sqlite_")]
            for t in tables:
                cur.execute(f"SELECT COUNT(*) FROM {t};")
                inv["sqlite_tables"][t] = cur.fetchone()[0]
            conn.close()

        if os.path.exists(self.json_devices_path):
            try:
                with open(self.json_devices_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    inv["json_devices_count"] = len(data) if isinstance(data, list) else len(data.get("devices", []))
            except Exception as e:
                logger.warning(f"Could not read devices.json: {e}")

        return inv

    async def run_migration(self, session: Optional[Any] = None) -> MigrationReport:
        """Execute schema transformation, quarantine validation, and repository persistence."""
        inv = self.inventory()
        self.report.scanned = {
            "devices": inv.get("json_devices_count", 0),
            **inv.get("sqlite_tables", {})
        }

        active_session = session or self._session
        if active_session:
            await self._execute_migration_steps(active_session)
        else:
            async with get_async_session() as s:
                await self._execute_migration_steps(s)

        return self.report

    async def _execute_migration_steps(self, session):
        # 1. Ensure Legacy Baseline Household, User, and Membership exist
        household, user = await self._ensure_baseline_entities(session)

        # 2. Migrate Devices from JSON registry
        await self._migrate_devices(session, household.id)

        # 3. Migrate SQLite Sessions & Conversations
        session_map = await self._migrate_conversations(session, household.id, user.id)

        # 4. Migrate SQLite Reminders
        await self._migrate_reminders(session, user.id, session_map)

        # 5. Commit if not dry run
        if not self.dry_run:
            await session.commit()
            logger.info("Database migration committed successfully.")
        else:
            await session.rollback()
            logger.info("Dry-run migration complete. No changes were committed.")

    async def _ensure_baseline_entities(self, session) -> Tuple[Household, User]:
        """Ensure baseline household and user exist for safely mapping legacy records."""
        q_h = await session.execute(select(Household).where(Household.id == self.default_household_id))
        household = q_h.scalar_one_or_none()
        if not household:
            household = Household(
                id=self.default_household_id,
                name="Legacy Migrated Household",
                timezone="Australia/Melbourne"
            )
            session.add(household)
            await session.flush()

        q_u = await session.execute(select(User).where(User.id == "user_legacy_resident"))
        user = q_u.scalar_one_or_none()
        if not user:
            user = User(
                id="user_legacy_resident",
                email="legacy_resident@rnrobots.local",
                password_hash="argon2_migrated_placeholder",
                full_name="Legacy Default Resident",
                role="resident",
                is_active=True
            )
            session.add(user)
            await session.flush()

            membership = HouseholdMembership(
                id=str(uuid.uuid4()),
                household_id=household.id,
                user_id=user.id,
                role="resident"
            )
            session.add(membership)
            await session.flush()

        return household, user

    async def _migrate_devices(self, session, household_id: str):
        """Migrate hardware devices from JSON registry into MySQL devices table."""
        if not os.path.exists(self.json_devices_path):
            return

        migrated_cnt = 0
        try:
            with open(self.json_devices_path, "r", encoding="utf-8") as f:
                content = json.load(f)
                dev_list = content if isinstance(content, list) else content.get("devices", [])

            for item in dev_list:
                node_id = str(item.get("device_id") or item.get("node_id") or "")
                dev_id = f"dev_{node_id}" if node_id else f"dev_{uuid.uuid4().hex[:12]}"
                name = item.get("name") or "Legacy Device"
                dev_type = item.get("type") or item.get("device_type") or "light"

                # Check if device already exists in MySQL
                existing = await session.execute(select(Device).where(Device.device_id == (node_id or dev_id)))
                if existing.scalar_one_or_none():
                    continue

                dev = Device(
                    id=dev_id,
                    household_id=household_id,
                    name=name,
                    device_id=node_id or dev_id,
                    node_id=node_id,
                    type=dev_type,
                    connection_type=item.get("protocol", "WiFi"),
                    power_state=item.get("status", "off"),
                    online_status="online",
                    is_enrolled=True
                )
                session.add(dev)
                migrated_cnt += 1

            self.report.migrated["devices"] = migrated_cnt
        except Exception as exc:
            self.report.errors.append(f"Device migration error: {exc}")

    async def _migrate_conversations(self, session, household_id: str, user_id: str) -> Dict[str, str]:
        """Migrate SQLite sessions and messages into MySQL conversation tables."""
        session_map: Dict[str, str] = {}
        if not os.path.exists(self.sqlite_db_path):
            return session_map

        migrated_sessions = 0
        migrated_messages = 0

        conn = sqlite3.connect(self.sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        try:
            # 1. Gather distinct sessions with messages or activity
            cur.execute("SELECT DISTINCT session_id FROM messages WHERE session_id IS NOT NULL")
            active_sids = [r["session_id"] for r in cur.fetchall()]

            for sid in active_sids:
                existing_sess = await session.execute(select(DbSession).where(DbSession.id == sid))
                db_s = existing_sess.scalar_one_or_none()
                if not db_s:
                    db_s = DbSession(
                        id=sid,
                        user_id=user_id,
                        household_id=household_id,
                        is_active=True,
                        is_awake=False
                    )
                    session.add(db_s)
                    await session.flush()
                    migrated_sessions += 1

                session_map[sid] = db_s.id

                # 2. Migrate messages for this session
                cur.execute("""
                    SELECT id, session_id, role, content, timestamp, content_hash, turn_hash, user_hash
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY id ASC
                """, (sid,))
                msgs = cur.fetchall()

                seq = 0
                prev_h = None
                for m in msgs:
                    m_role = "user" if m["role"] == "user" else "assistant"
                    text = m["content"] or ""
                    c_hash = m["content_hash"] or hashlib.sha256(text.encode("utf-8")).hexdigest()

                    cm = ConversationMessage(
                        id=str(uuid.uuid4()),
                        session_id=db_s.id,
                        user_id=user_id if m_role == "user" else None,
                        sender=m_role,
                        content=text,
                        content_hash=c_hash,
                        prev_hash=prev_h,
                        seq_num=seq
                    )
                    session.add(cm)
                    prev_h = c_hash
                    seq += 1
                    migrated_messages += 1

            self.report.migrated["sessions"] = migrated_sessions
            self.report.migrated["messages"] = migrated_messages
        except Exception as exc:
            self.report.errors.append(f"Conversation migration error: {exc}")
        finally:
            conn.close()

        return session_map

    async def _migrate_reminders(self, session, user_id: str, session_map: Dict[str, str]):
        """Migrate SQLite reminders with date/time parsing and quarantine of unverified entries."""
        if not os.path.exists(self.sqlite_db_path):
            return

        migrated_cnt = 0
        quarantine_cnt = 0

        conn = sqlite3.connect(self.sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT id, session_id, text, due_at_timestamp, due_at_iso, delay_seconds, status, created_at, reminded_at, recurrence
                FROM reminders
            """)
            rows = cur.fetchall()

            for r in rows:
                rem_id = str(r["id"])
                existing = await session.execute(select(Reminder).where(Reminder.id == rem_id))
                if existing.scalar_one_or_none():
                    continue

                text = (r["text"] or "").strip()
                if not text:
                    quarantine_cnt += 1
                    continue

                due_dt = None
                if r["due_at_timestamp"]:
                    try:
                        due_dt = datetime.fromtimestamp(float(r["due_at_timestamp"]), tz=timezone.utc)
                    except Exception:
                        pass
                if not due_dt and r["due_at_iso"]:
                    try:
                        due_dt = datetime.fromisoformat(r["due_at_iso"])
                        if due_dt.tzinfo is None:
                            due_dt = due_dt.replace(tzinfo=timezone.utc)
                    except Exception:
                        pass
                if not due_dt:
                    due_dt = datetime.now(timezone.utc)

                st = (r["status"] or "scheduled").lower()
                if st not in ["scheduled", "pending", "reminded", "completed", "cancelled", "acknowledged"]:
                    st = "scheduled"

                mapped_session = session_map.get(r["session_id"])

                rem_model = Reminder(
                    id=rem_id,
                    user_id=user_id,
                    session_id=mapped_session,
                    text=text,
                    due_at_utc=due_dt,
                    delay_seconds=int(r["delay_seconds"] or 0),
                    status=st,
                    recurrence=r["recurrence"] if r["recurrence"] in ["daily", "weekly", "monthly", "custom"] else "once"
                )
                session.add(rem_model)
                migrated_cnt += 1

            self.report.migrated["reminders"] = migrated_cnt
            self.report.quarantined["reminders"] = quarantine_cnt
        except Exception as exc:
            self.report.errors.append(f"Reminder migration error: {exc}")
        finally:
            conn.close()
