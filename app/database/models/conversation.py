"""Conversation persistence models: sessions, messages, and pending actions."""
from datetime import datetime, timezone
import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, utc_now
from app.database.types import JSONType


class Session(Base, TimestampMixin):
    """Conversational session binding identity, state, and recent context."""
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: f"session_{uuid.uuid4().hex[:12]}",
        index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    household_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("households.id", ondelete="SET NULL"), index=True, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_awake: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)

    # Relationships
    messages: Mapped[List["ConversationMessage"]] = relationship(
        "ConversationMessage", back_populates="session", cascade="all, delete-orphan", order_by="ConversationMessage.seq_num"
    )
    pending_actions: Mapped[List["PendingAction"]] = relationship(
        "PendingAction", back_populates="session", cascade="all, delete-orphan"
    )


class ConversationMessage(Base, UUIDPrimaryKeyMixin):
    """Cryptographically chained conversational message record."""
    __tablename__ = "conversation_messages"

    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    sender: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    prev_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    seq_num: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)

    # Relationships
    session: Mapped["Session"] = relationship("Session", back_populates="messages")


class PendingAction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Multi-turn pending action awaiting clarification or user confirmation."""
    __tablename__ = "pending_actions"

    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    missing_fields: Mapped[Optional[List[str]]] = mapped_column(JSONType, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)

    # Relationships
    session: Mapped["Session"] = relationship("Session", back_populates="pending_actions")

