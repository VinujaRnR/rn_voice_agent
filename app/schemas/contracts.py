"""Domain Pydantic request and response contracts decoupling API routes from internal services."""
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator


class ChatRequestContract(BaseModel):
    """Production request contract for Sarah conversational turns."""
    text: Optional[str] = Field(default=None, description="User transcribed or typed speech text")
    message: Optional[str] = Field(default=None, description="Alternative field for user message")
    session_id: Optional[str] = Field(default=None, description="Unique session ID. Omitted in legacy mode.")
    user_id: Optional[str] = Field(default=None, description="Authenticated user ID. Omitted in legacy mode.")
    household_id: Optional[str] = Field(default=None, description="Target household cluster ID.")
    enforce_wake_standby: Optional[bool] = Field(default=False, description="Enforce standby mode until wake word")

    def get_query(self) -> str:
        """Extract sanitized user text query."""
        return (self.text or self.message or "").strip()

    @model_validator(mode="after")
    def validate_non_empty(self):
        """Validate query text presence."""
        return self


class ChatResponseContract(BaseModel):
    """Standardized response contract returned to voice and chat clients."""
    mode: str = Field(..., description="Response mode: answer, device_command, clarify, action_scheduled")
    speech: str = Field(..., description="Spoken verbal text for Sarah TTS")
    command: Optional[Any] = Field(default=None, description="Verified device command payload")
    reminder: Optional[Any] = Field(default=None, description="Scheduled reminder specification")
    missing_fields: List[str] = Field(default_factory=list, description="Fields requiring user clarification")
    reasoning: Optional[str] = Field(default=None, description="Sarah LLM cognitive reasoning trace")
    session_id: Optional[str] = Field(default=None, description="Session ID for client continuity")


class DeviceControlRequestContract(BaseModel):
    """Contract for directly requesting IoT device state changes."""
    device_id: str = Field(..., description="Target device identifier or alias")
    action: str = Field(..., description="Action name, e.g. LIGHT_ON, set_power")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action parameter dictionary")
    user_id: Optional[str] = Field(default=None, description="Requesting user ID")
    session_id: Optional[str] = Field(default=None, description="Conversational context session ID")


class DeviceControlResponseContract(BaseModel):
    """Response contract for device dispatch actions."""
    status: str = Field(..., description="Execution status: success, validation_failed, failed")
    command_id: Optional[str] = Field(default=None, description="Unique command tracking UUID")
    destination: str = Field(default="RN Hub via RabbitMQ", description="Target IoT transport")
    published: bool = Field(default=False, description="Whether message was dispatched to transport")
    feedback: str = Field(..., description="Human-friendly verbal feedback")


class ReminderCreateRequestContract(BaseModel):
    """Contract for creating or scheduling care reminders."""
    text: str = Field(..., description="Reminder task description")
    delay_minutes: Optional[float] = Field(default=None, description="Delay in minutes")
    target_time: Optional[str] = Field(default=None, description="Absolute clock time (e.g. '04:00 PM')")
    recurrence: Optional[str] = Field(default="once", description="Recurrence frequency")
    user_id: Optional[str] = Field(default=None, description="Target resident user ID")
    session_id: Optional[str] = Field(default=None, description="Active session ID")


class ReminderResponseContract(BaseModel):
    """Response contract for reminder creation and query."""
    reminder_id: str = Field(..., description="Unique reminder tracking ID")
    text: str = Field(..., description="Reminder task description")
    due_at: Optional[str] = Field(default=None, description="Scheduled execution timestamp")
    delay_seconds: int = Field(default=0, description="Remaining seconds")
    status: str = Field(default="scheduled", description="Reminder status")
    recurrence: str = Field(default="once", description="Recurrence frequency")
    feedback: str = Field(..., description="Sarah spoken feedback")

