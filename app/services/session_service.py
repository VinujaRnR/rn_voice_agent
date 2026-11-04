"""Session and identity service with compatibility adapters for legacy frontend clients."""
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionContext:
    """Resolved execution context for an incoming user request."""
    session_id: str
    user_id: str
    household_id: Optional[str]
    is_legacy: bool
    is_authenticated: bool


class LegacySessionAdapter:
    """Temporary compatibility adapter allowing legacy frontend requests to function safely."""

    DEFAULT_FALLBACK_USER = "default_user"
    DEFAULT_FALLBACK_SESSION = "default_session"

    @classmethod
    def adapt(
        cls,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        household_id: Optional[str] = None
    ) -> SessionContext:
        """Resolve session and user identifiers, providing safe fallbacks for legacy clients."""
        is_legacy = False
        resolved_session = session_id
        resolved_user = user_id

        if not resolved_session or resolved_session == cls.DEFAULT_FALLBACK_SESSION:
            resolved_session = resolved_session or cls.DEFAULT_FALLBACK_SESSION
            is_legacy = True

        if not resolved_user or resolved_user == cls.DEFAULT_FALLBACK_USER:
            resolved_user = resolved_user or cls.DEFAULT_FALLBACK_USER
            is_legacy = True

        return SessionContext(
            session_id=resolved_session,
            user_id=resolved_user,
            household_id=household_id,
            is_legacy=is_legacy,
            is_authenticated=not is_legacy
        )


class SessionService:
    """Manages session resolution, activity state, and identity verification."""

    def __init__(self, adapter: Optional[LegacySessionAdapter] = None):
        self.adapter = adapter or LegacySessionAdapter()

    def resolve_context(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        household_id: Optional[str] = None
    ) -> SessionContext:
        """Resolve verified identity or apply compatibility adapter."""
        return self.adapter.adapt(
            session_id=session_id,
            user_id=user_id,
            household_id=household_id
        )


# Global singleton instance
session_service = SessionService()

