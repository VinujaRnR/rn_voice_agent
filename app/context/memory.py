"""Three-layer conversation memory: Current turn, Short-term memory, and Persistent preferences."""
from typing import Dict, Any, List, Optional
from app.conversation.storage import ConversationStorage


class ConversationMemory:
    """Manages multi-layer memory across current turn, short-term session context, and persistent preferences."""

    def __init__(self, storage: Optional[ConversationStorage] = None):
        self.storage = storage or ConversationStorage()
        # In-memory store for references (e.g. recently mentioned places or devices)
        self._referenced_entities: Dict[str, Dict[str, Any]] = {}
        # Persistent user preferences
        self._user_preferences: Dict[str, Dict[str, Any]] = {}

    def get_recent_messages(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve short-term dialogue history for the session."""
        return self.storage.get_session_messages(session_id, limit=limit)

    def record_turn(self, session_id: str, user_text: str, assistant_text: Optional[str] = None):
        """Record the dialogue turn in short-term memory."""
        self.storage.append_message(session_id, role="user", content=user_text)
        if assistant_text:
            self.storage.append_message(session_id, role="assistant", content=assistant_text)

    def set_referenced_entity(self, session_id: str, entity_type: str, entity_data: Any):
        """Track referenced entities (e.g., 'those lights', 'that restaurant')."""
        if session_id not in self._referenced_entities:
            self._referenced_entities[session_id] = {}
        self._referenced_entities[session_id][entity_type] = entity_data

    def get_referenced_entity(self, session_id: str, entity_type: str) -> Optional[Any]:
        """Retrieve the last referenced entity in context."""
        return self._referenced_entities.get(session_id, {}).get(entity_type)

    def get_preferences(self, user_id: str = "default_user") -> Dict[str, Any]:
        """Retrieve persistent preferences for the user."""
        return self._user_preferences.get(user_id, {
            "language": "en",
            "default_city": "Colombo",
            "country": "Sri Lanka",
            "timezone": "Asia/Colombo",
            "units": "celsius",
            "response_style": "conversational"
        })

    def update_preferences(self, user_id: str, prefs: Dict[str, Any]):
        """Update persistent user preferences."""
        current = self.get_preferences(user_id)
        current.update(prefs)
        self._user_preferences[user_id] = current


conversation_memory = ConversationMemory()
