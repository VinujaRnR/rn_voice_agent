"""Pydantic schemas for validating tool calling arguments in Gemini / Sarah."""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class GetCurrentTimeArgs(BaseModel):
    timezone: str = Field("Asia/Colombo", description="IANA timezone or major city name")


class GetWeatherArgs(BaseModel):
    city: str = Field("Colombo", description="City name")
    forecast_days: int = Field(1, ge=1, le=7, description="Number of forecast days")


class SearchWebArgs(BaseModel):
    query: str = Field(..., description="Search query string")


class SearchPlacesArgs(BaseModel):
    query: str = Field("restaurants", description="Category or name of place")
    location: str = Field("Colombo", description="City or area")


class ListDevicesArgs(BaseModel):
    pass


class GetDeviceStatusArgs(BaseModel):
    device_id: str = Field(..., description="Hardware device ID or name")


class ControlDeviceArgs(BaseModel):
    device_id: str = Field(..., description="Target device ID or name")
    action: str = Field(..., description="Action name, e.g. turn_on, turn_off, set_power")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")


class ScheduleDeviceActionArgs(BaseModel):
    device_id: str = Field(..., description="Target device ID or name")
    action: str = Field(..., description="Action name")
    delay_minutes: int = Field(15, ge=1, le=1440, description="Delay in minutes")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")


class SetReminderArgs(BaseModel):
    text: str = Field(..., description="Reminder description")
    delay_seconds: Optional[int] = Field(None, ge=1)
    delay_minutes: Optional[float] = Field(None, ge=0.1)
    target_time: Optional[str] = None
    recurrence: Optional[str] = None
    session_id: Optional[str] = None


class ListRemindersArgs(BaseModel):
    session_id: Optional[str] = None


class CancelReminderArgs(BaseModel):
    reminder_id: Optional[str] = Field("all", description="Target reminder ID, keyword, or 'all'")
    session_id: Optional[str] = None


class ClarifyWeatherArgs(BaseModel):
    pass


class ClarifyReminderArgs(BaseModel):
    verb: Optional[str] = None
    partial_task: Optional[str] = None
    time_label: Optional[str] = None


class SearchPastConversationsArgs(BaseModel):
    query: str = Field(..., description="Search query or keyword")
    session_id: Optional[str] = None


# Extended schemas for Steps 11-15
class FamilyContactArgs(BaseModel):
    action: str = Field("list", description="Action: list, call, message")
    name: Optional[str] = None
    message: Optional[str] = None


class MedicationScheduleArgs(BaseModel):
    action: str = Field("list", description="Action: list, check, log_taken")
    medication_name: Optional[str] = None


class SafetyCheckArgs(BaseModel):
    action: str = Field("status", description="Action: status, check_in, emergency_alert")


class FindLocalProviderArgs(BaseModel):
    category: str = Field(..., description="Service category: plumber, electrician, handyman, ndis, aged_care")
    suburb_or_postcode: Optional[str] = Field(None, description="Australian suburb or postcode")


class PlayMusicArgs(BaseModel):
    action: str = Field("play", description="Action: play, pause, next, previous, volume, favorite")
    query: Optional[str] = Field(None, description="Song title, artist, or genre")
    playlist_name: Optional[str] = Field(None, description="Playlist name")
    volume_level: Optional[float] = Field(None, ge=0.0, le=1.0)
