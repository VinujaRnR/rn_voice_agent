"""Schemas for Gemini's structured JSON responses with cross-field validation."""
from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator, model_serializer


class DeviceParameters(BaseModel):
    """Explicit parameters schema compatible with Gemini Developer API mode (no additionalProperties)."""
    model_config = ConfigDict(extra="ignore")

    state: Optional[str] = Field(default=None, description="Power or operational state: on, off, idle")
    value: Optional[str] = Field(default=None, description="Target value or level, e.g., temperature or brightness")
    mode: Optional[str] = Field(default=None, description="Operational mode, e.g., auto, cool, heat")
    speed: Optional[str] = Field(default=None, description="Speed setting: low, medium, high or numeric")
    duration: Optional[str] = Field(default=None, description="Duration in minutes or seconds")
    delay_minutes: Optional[str] = Field(default=None, description="Delay before execution in minutes")

    @model_serializer
    def serialize_model(self) -> Dict[str, Any]:
        """Serialize only non-null fields to maintain exact dictionary compatibility."""
        return {k: v for k, v in self.__dict__.items() if v is not None and not k.startswith("_")}

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key, None)

    def __setitem__(self, key: str, value: Any):
        setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        val = getattr(self, key, None)
        return val if val is not None else default

    def __contains__(self, key: str) -> bool:
        return getattr(self, key, None) is not None

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, dict):
            return self.serialize_model() == other
        return super().__eq__(other)

    def keys(self):
        return self.serialize_model().keys()

    def items(self):
        return self.serialize_model().items()


class DeviceCommand(BaseModel):
    device_id: str = Field(..., description="Target device ID or hardware identifier")
    action: str = Field(..., description="Action name, e.g., set_power, move, stop")
    parameters: DeviceParameters = Field(
        default_factory=DeviceParameters,
        description="Key-value parameters for the device action"
    )


class GeminiResponse(BaseModel):
    mode: Literal[
        "answer",
        "clarify",
        "confirm",
        "device_command"
    ] = Field(..., description="Response type classification")
    speech: Optional[str] = Field(
        default=None,
        description="Spoken text response for TTS, questions for clarify, or confirmation prompt"
    )
    command: Optional[DeviceCommand] = Field(
        default=None,
        description="Proposed device instruction if mode is device_command or confirm"
    )
    missing_fields: List[str] = Field(
        default_factory=list,
        description="List of missing parameters if mode is clarify"
    )

    @model_validator(mode="after")
    def validate_cross_fields(self) -> "GeminiResponse":
        # 1. A device_command response must have a command object
        if self.mode == "device_command":
            if self.command is None:
                raise ValueError("A device_command response must have a valid command object.")
            if not self.command.device_id or not self.command.action:
                raise ValueError("DeviceCommand must have non-empty device_id and action.")

        # 2. A clarify response must have a clarifying question in speech
        elif self.mode == "clarify":
            if not self.speech or not self.speech.strip():
                raise ValueError("A clarify response must include a question in speech.")

        # 3. A confirm response must have a prompt in speech
        elif self.mode == "confirm":
            if not self.speech or not self.speech.strip():
                raise ValueError("A confirm response must include a confirmation question in speech.")

        # 4. An answer response must have speech
        elif self.mode == "answer":
            if not self.speech or not self.speech.strip():
                raise ValueError("An answer response must include speech content.")

        return self

    def is_executable(self) -> bool:
        """Returns True only if the response is a fully validated device_command ready for verification."""
        try:
            return (
                self.mode == "device_command"
                and self.command is not None
                and bool(self.command.device_id.strip())
                and bool(self.command.action.strip())
                and len(self.missing_fields) == 0
            )
        except Exception:
            return False
