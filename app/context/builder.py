"""Dynamic request context builder for Gemini 3.5 Flash-Lite."""
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any, Optional
from app.context.memory import conversation_memory
from app.commands.device_registry import device_registry
from app.conversation.storage import ConversationStorage


class ContextBuilder:
    def __init__(self, storage: Optional[ConversationStorage] = None):
        self.storage = storage or ConversationStorage()

    def build_context(
        self,
        session_id: str,
        user_id: str = "default_user",
        precise_location: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """Build trusted dynamic context on every request turn."""
        prefs = conversation_memory.get_preferences(user_id)
        tz_name = prefs.get("timezone", "Asia/Colombo")

        try:
            now_dt = datetime.now(ZoneInfo(tz_name))
        except Exception:
            tz_name = "Asia/Colombo"
            now_dt = datetime.now(ZoneInfo("Asia/Colombo"))

        # Pending action if any
        pending_action = self.storage.get_pending_action(session_id)

        # Recent conversation messages (current session)
        recent = conversation_memory.get_recent_messages(session_id, limit=8)
        formatted_messages = [
            {
                "role": msg["role"],
                "content": msg["content"],
                "content_hash": msg.get("content_hash"),
                "turn_hash": msg.get("turn_hash"),
                "timestamp": msg.get("timestamp")
            }
            for msg in recent
        ]

        # Previous conversation references (cross-session hashed memory for future reference)
        past_refs = conversation_memory.get_references_summary(session_id=session_id, user_id=user_id, limit=6)

        # Available registered devices
        all_devices = device_registry.list_devices()
        sanitized_devices = [
            {
                "id": dev["id"],
                "name": dev["name"],
                "node_id": dev.get("node_id"),
                "type": dev.get("type", "generic"),
                "location": dev.get("location"),
                "status": dev.get("status", "unknown"),
                "allowed_actions": dev.get("allowed_actions", []),
                "connected_devices_count": dev.get("connected_devices_count", len(dev.get("connected_devices", []))),
                "connected_devices": dev.get("connected_devices", [])
            }
            for dev in all_devices
        ]

        return {
            "assistant": "RN Assistant",
            "runtime": {
                "timezone": tz_name,
                "current_datetime": now_dt.isoformat(),
                "formatted_time": now_dt.strftime("%I:%M %p"),
                "formatted_date": now_dt.strftime("%A, %d %B %Y")
            },
            "location": {
                "default_city": prefs.get("default_city", "Colombo"),
                "country": prefs.get("country", "Sri Lanka"),
                "precise_location": precise_location
            },
            "conversation": {
                "session_id": session_id,
                "pending_intent": pending_action,
                "recent_messages": formatted_messages,
                "past_references": past_refs
            },
            "devices": {
                "registry_source": "rn_hub",
                "available_devices": sanitized_devices
            },
            "user_preferences": {
                "language": prefs.get("language", "en"),
                "units": prefs.get("units", "celsius"),
                "response_style": prefs.get("response_style", "conversational")
            }
        }


context_builder = ContextBuilder()
