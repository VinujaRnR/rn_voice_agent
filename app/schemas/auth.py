"""Authentication and identity request/response schemas."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="User password")
    full_name: Optional[str] = Field(None, description="User's full name")
    role: str = Field("resident", description="User role: resident, family, caregiver, admin")
    phone_number: Optional[str] = Field(None, description="Contact phone number")
    household_name: Optional[str] = Field(None, description="Optional name for household creation")
    household_id: Optional[str] = Field(None, description="Optional existing household ID to join")


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")
    household_id: Optional[str] = Field(None, description="Household ID context (optional)")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    household_id: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserMeResponse(BaseModel):
    user_id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    household_id: Optional[str] = None
    households: List[Dict[str, Any]] = Field(default_factory=list)
    preferred_name: Optional[str] = None

