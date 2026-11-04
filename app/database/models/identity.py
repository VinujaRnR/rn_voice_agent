"""Identity domain models: users, households, memberships, resident profiles."""
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Integer, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, utc_now
from app.database.types import EncryptedString, EncryptedText


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User account model for residents, family, caregivers, and admins."""
    __tablename__ = "users"

    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="resident", index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    household_memberships: Mapped[List["HouseholdMembership"]] = relationship(
        "HouseholdMembership", back_populates="user", cascade="all, delete-orphan"
    )
    resident_profile: Mapped[Optional["ResidentProfile"]] = relationship(
        "ResidentProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    preferences: Mapped[Optional["UserPreference"]] = relationship(
        "UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Household(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Household cluster linking residents, family members, caregivers, and local IoT hubs."""
    __tablename__ = "households"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Australia/Sydney", nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    country: Mapped[str] = mapped_column(String(128), default="Australia", nullable=False)

    # Relationships
    memberships: Mapped[List["HouseholdMembership"]] = relationship(
        "HouseholdMembership", back_populates="household", cascade="all, delete-orphan"
    )
    devices: Mapped[List["Device"]] = relationship("Device", back_populates="household")
    gateways: Mapped[List["Gateway"]] = relationship("Gateway", back_populates="household")


class HouseholdMembership(Base, UUIDPrimaryKeyMixin):
    """Associates users with households under designated roles."""
    __tablename__ = "household_memberships"
    __table_args__ = (
        UniqueConstraint("household_id", "user_id", name="uq_household_user"),
        Base.__table_args__
    )

    household_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("households.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), default="member", nullable=False)
    joined_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)

    # Relationships
    household: Mapped["Household"] = relationship("Household", back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="household_memberships")


class ResidentProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Personal care profile for a resident including sensitive medical notes."""
    __tablename__ = "resident_profiles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    household_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("households.id", ondelete="SET NULL"), index=True, nullable=True
    )
    preferred_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    birth_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    medical_notes: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(EncryptedString, nullable=True)
    primary_language: Mapped[str] = mapped_column(String(32), default="en", nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="resident_profile")

