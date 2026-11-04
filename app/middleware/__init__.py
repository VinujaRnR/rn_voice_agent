"""Middleware and request context package."""
from app.middleware.request_context import (
    RequestContext,
    get_request_context,
    get_current_request_context,
    set_current_request_context,
    ROLE_PERMISSIONS
)
from app.middleware.authorization import (
    require_authenticated,
    require_role,
    require_permission
)
from app.middleware.tenant_isolation import (
    enforce_household_isolation,
    enforce_resident_access,
    TenantIsolationError
)
from app.middleware.consent import (
    verify_resident_consent,
    require_consent
)

__all__ = [
    "RequestContext",
    "get_request_context",
    "get_current_request_context",
    "set_current_request_context",
    "ROLE_PERMISSIONS",
    "require_authenticated",
    "require_role",
    "require_permission",
    "enforce_household_isolation",
    "enforce_resident_access",
    "TenantIsolationError",
    "verify_resident_consent",
    "require_consent",
]

