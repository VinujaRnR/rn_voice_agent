import sqlite3
import json
import os
import time
from typing import Dict, List, Any, Optional
from datetime import datetime


class ConversationStorage:
    def __init__(self, db_path: str = "voice_assistant.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode and foreign keys
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            # 1. sessions table with wake tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'default_user',
                    is_awake INTEGER DEFAULT 0,
                    last_active_at REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Ensure columns exist if migrating existing DB
            cursor = conn.execute("PRAGMA table_info(sessions);")
            existing_cols = {row[1] for row in cursor.fetchall()}
            if "is_awake" not in existing_cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN is_awake INTEGER DEFAULT 0;")
            if "last_active_at" not in existing_cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN last_active_at REAL DEFAULT 0;")

            # 2. messages table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);")

            # 3. pending_actions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL UNIQUE,
                    action TEXT NOT NULL,
                    target_device TEXT,
                    parameters TEXT DEFAULT '{}',
                    missing_fields TEXT DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pending_session ON pending_actions(session_id);")

            # 4. command_history table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS command_history (
                    command_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_device TEXT,
                    state TEXT NOT NULL DEFAULT 'validated',
                    parameters TEXT DEFAULT '{}',
                    result TEXT DEFAULT '{}',
                    error TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_command_session ON command_history(session_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_command_state ON command_history(state);")

            # Column migration check for command_history
            cursor = conn.execute("PRAGMA table_info(command_history);")
            cmd_cols = {row[1] for row in cursor.fetchall()}
            if "parameters" not in cmd_cols:
                conn.execute("ALTER TABLE command_history ADD COLUMN parameters TEXT DEFAULT '{}';")
            if "error" not in cmd_cols:
                conn.execute("ALTER TABLE command_history ADD COLUMN error TEXT;")
            if "updated_at" not in cmd_cols:
                conn.execute("ALTER TABLE command_history ADD COLUMN updated_at TEXT;")

            # 5. reminders and schedules table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    due_at_timestamp REAL NOT NULL,
                    due_at_iso TEXT NOT NULL,
                    delay_seconds INTEGER DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reminded_at TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_session ON reminders(session_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_at_timestamp);")

    # Session Management
    def ensure_session(self, session_id: str, user_id: str = "default_user"):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO sessions (session_id, user_id, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET updated_at=CURRENT_TIMESTAMP;
            """, (session_id, user_id))

    def wake_session(self, session_id: str, user_id: str = "default_user"):
        """Wake up the session and initialize the 5-minute activity timer."""
        now_ts = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO sessions (session_id, user_id, is_awake, last_active_at, updated_at)
                VALUES (?, ?, 1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET is_awake=1, last_active_at=?, updated_at=CURRENT_TIMESTAMP;
            """, (session_id, user_id, now_ts, now_ts))

    def touch_session(self, session_id: str):
        """Update last active timestamp to reset the 5-minute silence timer."""
        now_ts = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE sessions
                SET last_active_at=?, updated_at=CURRENT_TIMESTAMP
                WHERE session_id=?;
            """, (now_ts, session_id))

    def sleep_session(self, session_id: str):
        """Put Sarah session to sleep / off mode."""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE sessions
                SET is_awake=0, updated_at=CURRENT_TIMESTAMP
                WHERE session_id=?;
            """, (session_id,))

    def is_session_awake(self, session_id: str, timeout_seconds: int = 300) -> bool:
        """Check if Sarah is currently awake. Returns False if asleep or if 5 minutes have elapsed."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT is_awake, last_active_at FROM sessions WHERE session_id=?;", (session_id,))
            row = cursor.fetchone()
            if not row:
                return False
            is_awake = bool(row["is_awake"])
            last_active = float(row["last_active_at"] or 0)
            if is_awake:
                elapsed = time.time() - last_active
                if elapsed < timeout_seconds:
                    return True
                else:
                    # Silence exceeded 5 minutes -> auto sleep
                    conn.execute("UPDATE sessions SET is_awake=0, updated_at=CURRENT_TIMESTAMP WHERE session_id=?;", (session_id,))
                    return False
            return False

    def get_session_info(self, session_id: str, timeout_seconds: int = 300) -> Dict[str, Any]:
        """Get current session wake state and remaining active seconds."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT is_awake, last_active_at FROM sessions WHERE session_id=?;", (session_id,))
            row = cursor.fetchone()
            if not row:
                return {"is_awake": False, "remaining_seconds": 0}
            is_awake = bool(row["is_awake"])
            last_active = float(row["last_active_at"] or 0)
            elapsed = time.time() - last_active
            if is_awake and elapsed < timeout_seconds:
                return {"is_awake": True, "remaining_seconds": max(0, int(timeout_seconds - elapsed))}
            else:
                return {"is_awake": False, "remaining_seconds": 0}

    # Message Operations
    def append_message(self, session_id: str, role: str, content: str):
        self.ensure_session(session_id)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO messages (session_id, role, content)
                VALUES (?, ?, ?);
            """, (session_id, role, content))

    def get_session_messages(self, session_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        self.ensure_session(session_id)
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT role, content, timestamp FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?;
            """, (session_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def clear_session_messages(self, session_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?;", (session_id,))
            conn.execute("DELETE FROM pending_actions WHERE session_id = ?;", (session_id,))

    # Pending Action Operations
    def save_pending_action(
        self,
        session_id: str,
        action: str,
        target_device: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        missing_fields: Optional[List[str]] = None,
        status: str = "pending"
    ):
        self.ensure_session(session_id)
        params_json = json.dumps(parameters or {})
        missing_json = json.dumps(missing_fields or [])
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO pending_actions (session_id, action, target_device, parameters, missing_fields, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    action=excluded.action,
                    target_device=excluded.target_device,
                    parameters=excluded.parameters,
                    missing_fields=excluded.missing_fields,
                    status=excluded.status,
                    updated_at=CURRENT_TIMESTAMP;
            """, (session_id, action, target_device, params_json, missing_json, status))

    def get_pending_action(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT action, target_device, parameters, missing_fields, status, updated_at
                FROM pending_actions
                WHERE session_id = ? AND status = 'pending';
            """, (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            data["parameters"] = json.loads(data["parameters"])
            data["missing_fields"] = json.loads(data["missing_fields"])
            return data

    def resolve_pending_action(self, session_id: str):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE pending_actions
                SET status = 'resolved', updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?;
            """, (session_id,))

    def cancel_pending_action(self, session_id: str):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE pending_actions
                SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?;
            """, (session_id,))

    # Command History Operations
    def record_command(
        self,
        command_id: str,
        session_id: str = "default_session",
        action: str = "unknown",
        target_device: Optional[str] = None,
        state: str = "validated",
        result: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        self.ensure_session(session_id)
        result_json = json.dumps(result or {})
        params_json = json.dumps(parameters or {})
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO command_history (command_id, session_id, action, target_device, state, parameters, result, error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(command_id) DO UPDATE SET
                    state=excluded.state,
                    parameters=excluded.parameters,
                    result=excluded.result,
                    error=excluded.error,
                    updated_at=CURRENT_TIMESTAMP;
            """, (command_id, session_id, action, target_device, state, params_json, result_json, error))

    def update_command_state(
        self,
        command_id: str,
        state: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> bool:
        """Update lifecycle state of a command (validated, published, accepted, completed, rejected, failed, expired, unknown)."""
        with self._get_connection() as conn:
            if result is not None:
                result_json = json.dumps(result)
                cursor = conn.execute("""
                    UPDATE command_history
                    SET state = ?, result = ?, error = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE command_id = ?;
                """, (state, result_json, error, command_id))
            else:
                cursor = conn.execute("""
                    UPDATE command_history
                    SET state = ?, error = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE command_id = ?;
                """, (state, error, command_id))
            return cursor.rowcount > 0

    def get_command(self, command_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve command record and its execution state by command ID."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT command_id, session_id, action, target_device, state, parameters, result, error, timestamp, updated_at
                FROM command_history
                WHERE command_id = ?;
            """, (command_id,))
            row = cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            try:
                item["parameters"] = json.loads(item.get("parameters") or "{}")
            except Exception:
                item["parameters"] = {}
            try:
                item["result"] = json.loads(item.get("result") or "{}")
            except Exception:
                item["result"] = {}
            return item

    def get_command_history(self, session_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT command_id, action, target_device, state, parameters, result, error, timestamp, updated_at
                FROM command_history
                WHERE session_id = ?
                ORDER BY timestamp DESC;
            """, (session_id,))
            records = []
            for row in cursor.fetchall():
                item = dict(row)
                try:
                    item["result"] = json.loads(item.get("result") or "{}")
                except Exception:
                    item["result"] = {}
                try:
                    item["parameters"] = json.loads(item.get("parameters") or "{}")
                except Exception:
                    item["parameters"] = {}
                records.append(item)
            return records

    # Reminder & Schedule Operations
    def create_reminder(
        self,
        reminder_id: str,
        session_id: str,
        text: str,
        due_at_timestamp: float,
        due_at_iso: str,
        delay_seconds: int = 0
    ) -> Dict[str, Any]:
        self.ensure_session(session_id)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO reminders (id, session_id, text, due_at_timestamp, due_at_iso, delay_seconds, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
                ON CONFLICT(id) DO UPDATE SET
                    session_id=excluded.session_id,
                    text=excluded.text,
                    due_at_timestamp=excluded.due_at_timestamp,
                    due_at_iso=excluded.due_at_iso,
                    delay_seconds=excluded.delay_seconds,
                    status=excluded.status;
            """, (reminder_id, session_id, text, due_at_timestamp, due_at_iso, delay_seconds))
        return {
            "id": reminder_id,
            "session_id": session_id,
            "text": text,
            "due_at_timestamp": due_at_timestamp,
            "due_at_iso": due_at_iso,
            "delay_seconds": delay_seconds,
            "status": "pending"
        }

    def get_active_reminders(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            if session_id:
                cursor = conn.execute("""
                    SELECT id, session_id, text, due_at_timestamp, due_at_iso, delay_seconds, status, created_at
                    FROM reminders
                    WHERE session_id = ? AND status = 'pending'
                    ORDER BY due_at_timestamp ASC;
                """, (session_id,))
            else:
                cursor = conn.execute("""
                    SELECT id, session_id, text, due_at_timestamp, due_at_iso, delay_seconds, status, created_at
                    FROM reminders
                    WHERE status = 'pending'
                    ORDER BY due_at_timestamp ASC;
                """)
            return [dict(row) for row in cursor.fetchall()]

    def get_due_reminders(self, current_timestamp: Optional[float] = None) -> List[Dict[str, Any]]:
        ts = current_timestamp if current_timestamp is not None else time.time()
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, session_id, text, due_at_timestamp, due_at_iso, delay_seconds, status, created_at
                FROM reminders
                WHERE status = 'pending' AND due_at_timestamp <= ?
                ORDER BY due_at_timestamp ASC;
            """, (ts,))
            return [dict(row) for row in cursor.fetchall()]

    def mark_reminder_triggered(self, reminder_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                UPDATE reminders
                SET status = 'reminded', reminded_at = CURRENT_TIMESTAMP
                WHERE id = ?;
            """, (reminder_id,))
            return cursor.rowcount > 0

    def cancel_reminder(self, reminder_id: str, session_id: Optional[str] = None) -> bool:
        with self._get_connection() as conn:
            if session_id:
                cursor = conn.execute("""
                    UPDATE reminders
                    SET status = 'cancelled'
                    WHERE (id = ? OR text LIKE ?) AND session_id = ? AND status = 'pending';
                """, (reminder_id, f"%{reminder_id}%", session_id))
            else:
                cursor = conn.execute("""
                    UPDATE reminders
                    SET status = 'cancelled'
                    WHERE (id = ? OR text LIKE ?) AND status = 'pending';
                """, (reminder_id, f"%{reminder_id}%"))
            return cursor.rowcount > 0

    def clear_all_reminders(self, session_id: Optional[str] = None) -> int:
        with self._get_connection() as conn:
            if session_id:
                cursor = conn.execute("""
                    UPDATE reminders
                    SET status = 'cancelled'
                    WHERE session_id = ? AND status = 'pending';
                """, (session_id,))
            else:
                cursor = conn.execute("""
                    UPDATE reminders
                    SET status = 'cancelled'
                    WHERE status = 'pending';
                """)
            return cursor.rowcount
