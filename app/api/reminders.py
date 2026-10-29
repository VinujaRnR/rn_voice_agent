"""REST API endpoints for reminders and schedules."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from app.tools.reminders import (
    set_reminder,
    list_reminders,
    cancel_reminder,
    check_due_reminders,
    fired_reminders_log
)

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


class CreateReminderRequest(BaseModel):
    text: str = Field(..., description="The reminder task or message")
    delay_minutes: Optional[float] = Field(None, description="Delay in minutes until the reminder triggers")
    delay_seconds: Optional[int] = Field(None, description="Delay in seconds until the reminder triggers")
    session_id: Optional[str] = Field("default_session", description="Session identifier")


class CancelReminderRequest(BaseModel):
    reminder_id: str = Field(..., description="Reminder ID or keyword to cancel")
    session_id: Optional[str] = Field("default_session", description="Session identifier")


@router.post("/")
async def create_reminder_endpoint(payload: CreateReminderRequest):
    """Create and persist a scheduled reminder."""
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Reminder text cannot be empty.")
    
    result = set_reminder(
        text=payload.text.strip(),
        delay_seconds=payload.delay_seconds,
        delay_minutes=payload.delay_minutes,
        session_id=payload.session_id or "default_session"
    )
    return result


@router.get("/")
async def list_reminders_endpoint(session_id: Optional[str] = None):
    """List active scheduled reminders."""
    return list_reminders(session_id=session_id)


@router.get("/due")
async def check_due_endpoint():
    """Poll for reminders that have reached their trigger time."""
    due = check_due_reminders()
    return {
        "due_count": len(due),
        "triggered": due,
        "recent_history": fired_reminders_log[-20:]
    }


@router.delete("/{reminder_id}")
async def delete_reminder_endpoint(reminder_id: str, session_id: Optional[str] = None):
    """Cancel a scheduled reminder by ID."""
    result = cancel_reminder(reminder_id, session_id=session_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return result

