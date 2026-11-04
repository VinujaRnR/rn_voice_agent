"""Database models package exporting all domain models across all steps."""
from app.database.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, utc_now
from app.database.types import EncryptedString, EncryptedText, UTCDateTime, JSONType
from app.database.models.identity import User, Household, HouseholdMembership, ResidentProfile
from app.database.models.authorization import AccessGrant, ConsentRecord, Representative
from app.database.models.conversation import Session, ConversationMessage, PendingAction
from app.database.models.personalization import UserPreference, PersonalMemory
from app.database.models.devices import (
    Device, DeviceCapability, Gateway, DeviceBinding,
    DeviceState, DeviceTelemetry, DeviceCommandLog, DeviceEnrollmentRequest
)
from app.database.models.reminders import Reminder, RecurrenceRule, ReminderOccurrence
from app.database.models.family import FamilyContact, FamilyEvent, FamilyMessage
from app.database.models.care import (
    Caregiver, CaregiverAssignment, CarePlan, MedicationSchedule, MedicationEvent, CareEscalation
)
from app.database.models.safety import SensorEvent, SafetyRule, SafetyIncident, ExternalAlert
from app.database.models.entertainment import Track, Playlist, PlaylistTrack, UserFavorite

__all__ = [
    "Base",
    "UUIDPrimaryKeyMixin",
    "TimestampMixin",
    "utc_now",
    "EncryptedString",
    "EncryptedText",
    "UTCDateTime",
    "JSONType",
    "User",
    "Household",
    "HouseholdMembership",
    "ResidentProfile",
    "AccessGrant",
    "ConsentRecord",
    "Representative",
    "Session",
    "ConversationMessage",
    "PendingAction",
    "UserPreference",
    "PersonalMemory",
    "Device",
    "DeviceCapability",
    "Gateway",
    "DeviceBinding",
    "DeviceState",
    "DeviceTelemetry",
    "DeviceCommandLog",
    "DeviceEnrollmentRequest",
    "Reminder",
    "RecurrenceRule",
    "ReminderOccurrence",
    "FamilyContact",
    "FamilyEvent",
    "FamilyMessage",
    "Caregiver",
    "CaregiverAssignment",
    "CarePlan",
    "MedicationSchedule",
    "MedicationEvent",
    "CareEscalation",
    "SensorEvent",
    "SafetyRule",
    "SafetyIncident",
    "ExternalAlert",
    "Track",
    "Playlist",
    "PlaylistTrack",
    "UserFavorite",
]
