"""Session helper for tracking active sessions and wake states."""
from typing import Dict, Any, Optional
from app.conversation.storage import ConversationStorage


class SessionService:
    def __init__(self, storage: Optional[ConversationStorage] = None):
        self.storage = storage or ConversationStorage()

    def get_session_status(self, session_id: str, timeout_seconds: int = 300) -> Dict[str, Any]:
        return self.storage.get_session_info(session_id, timeout_seconds=timeout_seconds)

    def wake_session(self, session_id: str, user_id: str = "default_user"):
        self.storage.wake_session(session_id, user_id=user_id)

    def touch_session(self, session_id: str):
        self.storage.touch_session(session_id)

    def sleep_session(self, session_id: str):
        self.storage.sleep_session(session_id)


session_service = SessionService()
