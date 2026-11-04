"""Care reminder service providing scheduling, querying, and recurrence management."""
from typing import Optional, List, Dict, Any
from app.tools.reminders import (
    set_reminder,
    list_reminders,
    cancel_reminder,
    update_reminder_recurrence,
    parse_reminder_expression
)
from app.schemas.contracts import ReminderCreateRequestContract, ReminderResponseContract


class ReminderService:
    """Service encapsulating reminder business logic and persistence."""

    def create_reminder(self, request: ReminderCreateRequestContract) -> ReminderResponseContract:
        """Create a scheduled reminder from contract."""
        res = set_reminder(
            text=request.text,
            delay_minutes=request.delay_minutes,
            target_time=request.target_time,
            session_id=request.session_id or "default_session",
            recurrence=request.recurrence
        )
        return ReminderResponseContract(
            reminder_id=res.get("reminder_id", ""),
            text=res.get("text", request.text),
            due_at=res.get("due_at"),
            delay_seconds=res.get("delay_seconds", 0),
            status=res.get("status", "scheduled"),
            recurrence=res.get("recurrence", "once"),
            feedback=res.get("feedback", "Reminder set.")
        )

    def list_active(self, session_id: str = "default_session") -> List[Dict[str, Any]]:
        """Retrieve active reminders for a session."""
        from app.conversation.storage import ConversationStorage
        items = ConversationStorage().get_active_reminders(session_id=session_id)
        for item in items:
            if "id" in item and "reminder_id" not in item:
                item["reminder_id"] = item["id"]
        return items

    def cancel(self, reminder_id: str, session_id: str = "default_session") -> bool:
        """Cancel an active reminder."""
        res = cancel_reminder(reminder_id, session_id=session_id)
        return bool(res.get("cancelled", False) or res.get("status") in ["success", "cancelled"] or res.get("count", 0) > 0)

    def update_recurrence(self, reminder_id: str, recurrence: str, session_id: str = "default_session") -> Dict[str, Any]:
        """Update recurrence rule for a reminder."""
        return update_reminder_recurrence(reminder_id, recurrence, session_id=session_id)


# Global singleton instance
reminder_service = ReminderService()
