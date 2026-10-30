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
        """Retrieve short-term dialogue history for the session (with cryptographic hashes)."""
        return self.storage.get_session_messages(session_id, limit=limit)

    def record_turn(
        self,
        session_id: str,
        user_text: str,
        assistant_text: Optional[str] = None,
        user_id: str = "default_user"
    ):
        """Record the dialogue turn in memory, hashed for future references."""
        self.storage.append_message(session_id, role="user", content=user_text, user_id=user_id)
        if assistant_text:
            self.storage.append_message(session_id, role="assistant", content=assistant_text, user_id=user_id)

    def get_previous_conversations(
        self,
        user_id: str = "default_user",
        limit: int = 15,
        exclude_session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve previous stored conversations for future references."""
        return self.storage.get_user_previous_conversations(
            user_id=user_id,
            limit=limit,
            exclude_session_id=exclude_session_id
        )

    def search_past_conversations(
        self,
        query: str,
        user_id: str = "default_user",
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search past conversations by keyword, query, or hash match for recall."""
        return self.storage.search_previous_conversations(
            query=query,
            user_id=user_id,
            limit=limit
        )

    def get_references_summary(
        self,
        session_id: str,
        user_id: str = "default_user",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get summarized previous interactions for future reference in Gemini dynamic context."""
        past_turns = self.get_previous_conversations(user_id=user_id, limit=limit, exclude_session_id=session_id)
        return [
            {
                "session_id": t["session_id"],
                "role": t["role"],
                "content": t["content"],
                "content_hash": t["content_hash"],
                "turn_hash": t["turn_hash"],
                "timestamp": t.get("timestamp")
            }
            for t in past_turns
        ]

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

    def clear_memory(self, session_id: Optional[str] = None, clear_all: bool = False):
        """Clear cached referenced entities and session memory."""
        if clear_all or not session_id:
            self._referenced_entities.clear()
        elif session_id in self._referenced_entities:
            del self._referenced_entities[session_id]


conversation_memory = ConversationMemory()
