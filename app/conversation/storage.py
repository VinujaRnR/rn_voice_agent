import sqlite3
import json
import os
import re
import time
import hashlib
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime


def compute_content_hash(text: str) -> str:
    """Compute deterministic SHA-256 cryptographic digest of message text."""
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


def compute_user_hash(user_id: str) -> str:
    """Compute deterministic SHA-256 hash of user ID for privacy-preserving indexing."""
    return hashlib.sha256((user_id or "default_user").strip().encode("utf-8")).hexdigest()


def compute_turn_hash(session_id: str, role: str, content: str, timestamp: Optional[str] = None) -> str:
    """Compute SHA-256 hash of a full conversational turn for integrity and reference lookup."""
    raw = f"{session_id}:{role}:{(content or '').strip()}:{timestamp or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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

            # 2. messages table with cryptographic hash tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT,
                    turn_hash TEXT,
                    user_hash TEXT DEFAULT 'default_user',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);")

            # Check and migrate columns for messages table
            cursor = conn.execute("PRAGMA table_info(messages);")
            msg_cols = {row[1] for row in cursor.fetchall()}
            if "content_hash" not in msg_cols:
                conn.execute("ALTER TABLE messages ADD COLUMN content_hash TEXT;")
            if "turn_hash" not in msg_cols:
                conn.execute("ALTER TABLE messages ADD COLUMN turn_hash TEXT;")
            if "user_hash" not in msg_cols:
                conn.execute("ALTER TABLE messages ADD COLUMN user_hash TEXT DEFAULT 'default_user';")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_content_hash ON messages(content_hash);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_turn_hash ON messages(turn_hash);")

            # Retroactive backfill for existing message rows without hashes
            try:
                unhashed_cursor = conn.execute("SELECT id, session_id, role, content, timestamp FROM messages WHERE content_hash IS NULL;")
                for r in unhashed_cursor.fetchall():
                    c_hash = compute_content_hash(r["content"])
                    t_hash = compute_turn_hash(r["session_id"], r["role"], r["content"], str(r["timestamp"]))
                    u_hash = compute_user_hash("default_user")
                    conn.execute("UPDATE messages SET content_hash=?, turn_hash=?, user_hash=? WHERE id=?;", (c_hash, t_hash, u_hash, r["id"]))
            except Exception:
                pass

            # 2b. conversation_references table for long-term cross-session recall and future reference
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_references (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reference_id TEXT UNIQUE,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT 'default_user',
                    user_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    turn_hash TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_ref_user_hash ON conversation_references(user_hash);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_ref_content_hash ON conversation_references(content_hash);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_ref_turn_hash ON conversation_references(turn_hash);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_ref_session ON conversation_references(session_id);")

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

    # Message Operations & Hashed Conversation References
    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """Append a message turn to storage, computing and persisting SHA-256 cryptographic hashes for future reference."""
        self.ensure_session(session_id, user_id=user_id)
        c_hash = compute_content_hash(content)
        u_hash = compute_user_hash(user_id)
        ref_id = f"ref_{uuid.uuid4().hex[:10]}"
        now_ts = datetime.now().isoformat()
        t_hash = compute_turn_hash(session_id, role, content, now_ts)

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO messages (session_id, role, content, content_hash, turn_hash, user_hash, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
            """, (session_id, role, content, c_hash, t_hash, u_hash))

            # Store in conversation_references for cross-session recall and future reference
            conn.execute("""
                INSERT INTO conversation_references (
                    reference_id, session_id, user_id, user_hash, role, content, content_hash, turn_hash, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
            """, (ref_id, session_id, user_id, u_hash, role, content, c_hash, t_hash))

        return {
            "session_id": session_id,
            "role": role,
            "content": content,
            "content_hash": c_hash,
            "turn_hash": t_hash,
            "user_hash": u_hash
        }

    def get_session_messages(self, session_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        self.ensure_session(session_id)
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, session_id, role, content, content_hash, turn_hash, user_hash, timestamp FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?;
            """, (session_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_user_previous_conversations(
        self,
        user_id: str = "default_user",
        limit: int = 20,
        exclude_session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve user's previous conversations across sessions for future reference."""
        u_hash = compute_user_hash(user_id)
        with self._get_connection() as conn:
            if exclude_session_id:
                cursor = conn.execute("""
                    SELECT reference_id, session_id, user_id, user_hash, role, content, content_hash, turn_hash, timestamp
                    FROM conversation_references
                    WHERE (user_id = ? OR user_hash = ?) AND session_id != ?
                    ORDER BY id DESC
                    LIMIT ?;
                """, (user_id, u_hash, exclude_session_id, limit))
            else:
                cursor = conn.execute("""
                    SELECT reference_id, session_id, user_id, user_hash, role, content, content_hash, turn_hash, timestamp
                    FROM conversation_references
                    WHERE (user_id = ? OR user_hash = ?)
                    ORDER BY id DESC
                    LIMIT ?;
                """, (user_id, u_hash, limit))
            return [dict(row) for row in cursor.fetchall()]

    def search_previous_conversations(
        self,
        query: str,
        user_id: str = "default_user",
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search previous conversation turns by text, topic, or hash match for future reference."""
        clean_q = (query or "").strip().lower()
        u_hash = compute_user_hash(user_id)

        with self._get_connection() as conn:
            # If query is empty (general recall e.g. "what did we talk about"), return most recent references
            if not clean_q:
                cursor = conn.execute("""
                    SELECT reference_id, session_id, role, content, content_hash, turn_hash, timestamp
                    FROM conversation_references
                    WHERE (user_id = ? OR user_hash = ?)
                    ORDER BY id DESC
                    LIMIT ?;
                """, (user_id, u_hash, limit))
                return [dict(row) for row in cursor.fetchall()]

            target_hash = compute_content_hash(clean_q)
            stop_words = {"what", "which", "where", "when", "about", "that", "this", "there", "have", "with", "from", "tell", "said", "talk", "discuss", "remember", "recall"}
            keywords = [w for w in re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", clean_q) if w not in stop_words]

            # Primary match: full substring, hash, or turn_hash
            cursor = conn.execute("""
                SELECT reference_id, session_id, role, content, content_hash, turn_hash, timestamp
                FROM conversation_references
                WHERE (user_id = ? OR user_hash = ?)
                  AND (LOWER(content) LIKE ? OR content_hash = ? OR turn_hash LIKE ?)
                ORDER BY id DESC
                LIMIT ?;
            """, (user_id, u_hash, f"%{clean_q}%", target_hash, f"{clean_q}%", limit))
            results = [dict(row) for row in cursor.fetchall()]

            # Keyword fallback if exact full string had no matches and keywords exist
            if not results and keywords:
                for kw in keywords[:3]:
                    c_kw = conn.execute("""
                        SELECT reference_id, session_id, role, content, content_hash, turn_hash, timestamp
                        FROM conversation_references
                        WHERE (user_id = ? OR user_hash = ?)
                          AND LOWER(content) LIKE ?
                        ORDER BY id DESC
                        LIMIT ?;
                    """, (user_id, u_hash, f"%{kw}%", limit))
                    kw_rows = [dict(row) for row in c_kw.fetchall()]
                    for r in kw_rows:
                        if not any(existing["reference_id"] == r["reference_id"] for existing in results):
                            results.append(r)
                    if len(results) >= limit:
                        break

            return results[:limit]

    def get_conversation_by_hash(self, hash_value: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific stored conversation turn by its content_hash or turn_hash."""
        clean_hash = (hash_value or "").strip().lower()
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT reference_id, session_id, role, content, content_hash, turn_hash, timestamp
                FROM conversation_references
                WHERE content_hash = ? OR turn_hash = ?
                LIMIT 1;
            """, (clean_hash, clean_hash))
            row = cursor.fetchone()
            return dict(row) if row else None

    def clear_session_messages(self, session_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?;", (session_id,))
            conn.execute("DELETE FROM conversation_references WHERE session_id = ?;", (session_id,))
            conn.execute("DELETE FROM pending_actions WHERE session_id = ?;", (session_id,))

    def clear_conversation_history(self, session_id: Optional[str] = None, user_id: Optional[str] = None, clear_all: bool = False) -> int:
        """Clear conversation history, references, and pending actions from database."""
        deleted_count = 0
        with self._get_connection() as conn:
            if clear_all or not session_id:
                c1 = conn.execute("DELETE FROM messages;")
                c2 = conn.execute("DELETE FROM conversation_references;")
                c3 = conn.execute("DELETE FROM pending_actions;")
                deleted_count = (c1.rowcount or 0) + (c2.rowcount or 0)
            else:
                c1 = conn.execute("DELETE FROM messages WHERE session_id = ?;", (session_id,))
                c2 = conn.execute("DELETE FROM conversation_references WHERE session_id = ?;", (session_id,))
                c3 = conn.execute("DELETE FROM pending_actions WHERE session_id = ?;", (session_id,))
                deleted_count = (c1.rowcount or 0) + (c2.rowcount or 0)
        return deleted_count

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

    def get_due_or_recently_triggered_reminders(self, current_timestamp: Optional[float] = None, window_seconds: float = 120.0) -> List[Dict[str, Any]]:
        ts = current_timestamp if current_timestamp is not None else time.time()
        min_ts = ts - window_seconds
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, session_id, text, due_at_timestamp, due_at_iso, delay_seconds, status, created_at, reminded_at
                FROM reminders
                WHERE (status = 'pending' AND due_at_timestamp <= ?)
                   OR (status = 'reminded' AND due_at_timestamp >= ? AND due_at_timestamp <= ?)
                ORDER BY due_at_timestamp ASC;
            """, (ts, min_ts, ts + 15))
            return [dict(row) for row in cursor.fetchall()]

    def mark_reminder_triggered(self, reminder_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                UPDATE reminders
                SET status = 'reminded', reminded_at = CURRENT_TIMESTAMP
                WHERE id = ?;
            """, (reminder_id,))
            return cursor.rowcount > 0

    def mark_reminder_acknowledged(self, reminder_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                UPDATE reminders
                SET status = 'acknowledged', reminded_at = CURRENT_TIMESTAMP
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
