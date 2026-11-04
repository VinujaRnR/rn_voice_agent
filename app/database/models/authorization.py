"""Authorization, consent, and representative models."""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, utc_now


class AccessGrant(Base, UUIDPrimaryKeyMixin):
    """Explicit scoped permission granted by a resident to family or caregiver."""
    __tablename__ = "access_grants"

    granter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    grantee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scope: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)

    # Relationships
    granter: Mapped["User"] = relationship("User", foreign_keys=[granter_id])
    grantee: Mapped["User"] = relationship("User", foreign_keys=[grantee_id])


class ConsentRecord(Base, UUIDPrimaryKeyMixin):
    """Tracks explicit resident consent for sensitive services."""
    __tablename__ = "consent_records"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    consent_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    is_granted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User")


class Representative(Base, UUIDPrimaryKeyMixin):
    """Designated legal or family representative for a resident."""
    __tablename__ = "representatives"

    resident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    representative_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)

    # Relationships
    resident: Mapped["User"] = relationship("User", foreign_keys=[resident_id])
    representative: Mapped["User"] = relationship("User", foreign_keys=[representative_id])

