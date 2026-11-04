"""Role-based and permission-based authorization dependencies."""
from typing import Callable, Sequence
from fastapi import Depends, HTTPException, status
from app.middleware.request_context import RequestContext, get_request_context


def require_authenticated(ctx: RequestContext = Depends(get_request_context)) -> RequestContext:
    """Dependency enforcing that caller must be authenticated with valid JWT."""
    if not ctx.is_authenticated or ctx.is_legacy:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for this operation"
        )
    return ctx


def require_role(*roles: str) -> Callable:
    """Dependency factory checking that the authenticated caller has one of the allowed roles."""
    async def role_checker(ctx: RequestContext = Depends(require_authenticated)) -> RequestContext:
        if not ctx.has_role(*roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Requires one of roles {roles}, but user has '{ctx.role}'"
            )
        return ctx
    return role_checker


def require_permission(*permissions: str) -> Callable:
    """Dependency factory checking that caller has all required permissions."""
    async def permission_checker(ctx: RequestContext = Depends(require_authenticated)) -> RequestContext:
        for perm in permissions:
            if not ctx.has_permission(perm):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: Missing required permission '{perm}'"
                )
        return ctx
    return permission_checker

