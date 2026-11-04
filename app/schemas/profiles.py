"""Schemas for resident profiles, personalization preferences, memories, and access grants."""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class ResidentProfileResponse(BaseModel):
    id: str
    user_id: str
    household_id: Optional[str] = None
    preferred_name: Optional[str] = None
    birth_year: Optional[int] = None
    primary_language: str = "en"
    medical_notes: Optional[str] = None
    emergency_contact_phone: Optional[str] = None


class ResidentProfileUpdateRequest(BaseModel):
    preferred_name: Optional[str] = Field(None, description="Preferred name for conversational address")
    birth_year: Optional[int] = Field(None, description="Birth year")
    primary_language: Optional[str] = Field(None, description="Preferred language, e.g. 'en'")
    medical_notes: Optional[str] = Field(None, description="Medical notes and care guidelines")
    emergency_contact_phone: Optional[str] = Field(None, description="Emergency contact phone number")


class ResidentPreferenceResponse(BaseModel):
    user_id: str
    wake_word: str = "Sarah"
    voice_name: str = "en-US-JennyNeural"
    speaking_rate: float = 1.0
    volume: float = 1.0
    temperature_unit: str = "celsius"


class ResidentPreferenceUpdateRequest(BaseModel):
    wake_word: Optional[str] = Field(None, description="Custom wake word (default: Sarah)")
    voice_name: Optional[str] = Field(None, description="Edge TTS voice name (default: en-US-JennyNeural)")
    speaking_rate: Optional[float] = Field(None, ge=0.5, le=2.0, description="Speaking rate multiplier")
    volume: Optional[float] = Field(None, ge=0.0, le=1.0, description="Volume level")
    temperature_unit: Optional[str] = Field(None, description="'celsius' or 'fahrenheit'")


class MemoryCreateRequest(BaseModel):
    memory_key: str = Field(..., description="Unique memory topic/key, e.g. 'grandson_name'")
    memory_value: str = Field(..., description="Memory details/facts")
    category: str = Field("general", description="Category: family, health, routine, preference, general")
    importance_score: int = Field(5, ge=1, le=10, description="Importance score from 1 to 10")


class MemoryResponse(BaseModel):
    id: str
    user_id: str
    memory_key: str
    memory_value: str
    category: str
    importance_score: int
    created_at: Optional[str] = None


class AccessGrantCreateRequest(BaseModel):
    grantee_id: str = Field(..., description="User ID receiving permission")
    scope: str = Field(..., description="Scope string, e.g. 'profile:read', 'medical_data', 'reminder:write'")
    expires_at: Optional[datetime] = Field(None, description="Optional expiration timestamp")


class AccessGrantResponse(BaseModel):
    id: str
    granter_id: str
    grantee_id: str
    scope: str
    status: str
    expires_at: Optional[str] = None


class ConsentRecordRequest(BaseModel):
    consent_type: str = Field(..., description="Consent type, e.g. 'medical_data', 'voice_recording'")
    is_granted: bool = Field(True, description="Whether consent is active or revoked")

