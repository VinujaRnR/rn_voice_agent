"""Request context abstraction for multi-user, multi-tenant Sarah AI platform."""
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional, List, Set, Dict, Any
from fastapi import Request, Header, HTTPException, status
import jwt

from app.security.auth import decode_token

# Role default permission mapping
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "admin": {"*"},
    "resident": {
        "profile:read", "profile:write",
        "conversation:read", "conversation:write",
        "device:read", "device:control",
        "reminder:read", "reminder:write", "reminder:cancel",
        "family:read", "family:write",
        "care:read"
    },
    "family": {
        "profile:read", "profile:write",
        "conversation:read", "conversation:write",
        "device:read", "device:control",
        "reminder:read", "reminder:write",
        "family:read", "family:write",
        "care:read"
    },
    "caregiver": {
        "profile:read", "profile:write",
        "device:read", "device:control",
        "reminder:read", "reminder:write", "reminder:cancel",
        "family:read", "family:write",
        "care:read", "care:write"
    },
    "device": {
        "device:telemetry", "device:heartbeat", "device:control"
    },
    "guest": {
        "conversation:write", "device:read", "family:write"
    }
}


@dataclass
class RequestContext:
    """Thread-safe and async-safe request context for multi-user isolation."""
    actor_id: str
    user_id: Optional[str] = None
    household_id: Optional[str] = None
    resident_id: Optional[str] = None
    session_id: str = "default_session"
    role: str = "resident"
    permissions: List[str] = field(default_factory=list)
    email: Optional[str] = None
    is_authenticated: bool = False
    is_legacy: bool = True
    auth_token: Optional[str] = None

    def has_permission(self, permission: str) -> bool:
        """Check if context holds permission (or wildcard '*' from admin)."""
        if self.is_legacy or "*" in self.permissions or self.role == "admin":
            return True
        return permission in self.permissions

    def has_role(self, *roles: str) -> bool:
        """Check if actor role matches any of the given roles."""
        return self.role in roles or self.role == "admin"


# Context variable for background tasks or deep service access
_request_context_var: ContextVar[Optional[RequestContext]] = ContextVar("request_context", default=None)


def get_current_request_context() -> Optional[RequestContext]:
    """Retrieve current context from contextvars."""
    return _request_context_var.get()


def set_current_request_context(ctx: RequestContext):
    """Set current context in contextvars."""
    return _request_context_var.set(ctx)


async def get_request_context(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_household_id: Optional[str] = Header(None, alias="X-Household-ID"),
    x_resident_id: Optional[str] = Header(None, alias="X-Resident-ID"),
) -> RequestContext:
    """FastAPI Dependency resolving multi-tenant request context.
    
    If Bearer token is provided:
        Decodes JWT, verifies issuer & expiration, extracts claims (sub, role, household_id, permissions).
    If NO token is provided:
        Gracefully resolves via LegacySessionAdapter to maintain backward compatibility
        for existing hardware endpoints, local developer runs, and legacy test suites.
    """
    token: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    if token:
        try:
            payload = decode_token(token)
            user_id = str(payload.get("sub", ""))
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: missing subject"
                )

            role = str(payload.get("role", "resident"))
            household_id = payload.get("household_id") or x_household_id
            resident_id = payload.get("resident_id") or x_resident_id or (user_id if role == "resident" else None)

            # Derive permissions
            token_perms = payload.get("permissions")
            if token_perms and isinstance(token_perms, list):
                permissions = list(token_perms)
            else:
                permissions = list(ROLE_PERMISSIONS.get(role, set()))

            session_id = x_session_id or f"sess_{user_id[:8]}"
            email = payload.get("email")

            ctx = RequestContext(
                actor_id=user_id,
                user_id=user_id,
                household_id=str(household_id) if household_id else None,
                resident_id=str(resident_id) if resident_id else None,
                session_id=session_id,
                role=role,
                permissions=permissions,
                email=str(email) if email else None,
                is_authenticated=True,
                is_legacy=False,
                auth_token=token
            )
            set_current_request_context(ctx)
            return ctx

        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired"
            )
        except jwt.InvalidTokenError as err:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid authentication token: {str(err)}"
            )

    # Legacy Fallback: seamless compatibility with legacy hardware and tests
    from app.services.session_service import LegacySessionAdapter
    legacy_session = LegacySessionAdapter.adapt(
        session_id=x_session_id,
        user_id=None,
        household_id=x_household_id
    )
    ctx = RequestContext(
        actor_id=legacy_session.user_id,
        user_id=legacy_session.user_id,
        household_id=legacy_session.household_id,
        resident_id=str(x_resident_id) if x_resident_id else legacy_session.user_id,
        session_id=legacy_session.session_id,
        role="resident",
        permissions=list(ROLE_PERMISSIONS["resident"]),
        is_authenticated=False,
        is_legacy=True
    )
    set_current_request_context(ctx)
    return ctx
