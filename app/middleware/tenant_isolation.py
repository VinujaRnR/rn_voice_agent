"""Tenant and household isolation middleware and enforcement functions."""
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.middleware.request_context import RequestContext
from app.database.repositories.auth_repository import AuthRepository


class TenantIsolationError(HTTPException):
    def __init__(self, detail: str = "Tenant boundary violation: access denied"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def enforce_household_isolation(ctx: RequestContext, resource_household_id: Optional[str]) -> None:
    """Ensure actor only accesses resources within their assigned household.
    
    Args:
        ctx: Caller RequestContext.
        resource_household_id: The household ID of the target resource.
        
    Raises:
        TenantIsolationError: If actor's household differs from the target resource's household.
    """
    if ctx.is_legacy or ctx.role == "admin":
        return

    if not resource_household_id:
        return

    if not ctx.household_id:
        raise TenantIsolationError("Actor does not belong to any household")

    if ctx.household_id != resource_household_id:
        raise TenantIsolationError(
            f"Tenant boundary violation: Actor household '{ctx.household_id}' "
            f"cannot access resource in household '{resource_household_id}'"
        )


async def enforce_resident_access(
    ctx: RequestContext,
    target_resident_id: str,
    scope: str,
    session: Optional[AsyncSession] = None
) -> None:
    """Verify actor has permission to access a specific resident's protected data.
    
    Rules:
    1. Legacy callers or admins have full access.
    2. Resident accessing their own data has full access.
    3. Family / Caregivers:
       - Must have access grant or active verified representative status or appropriate household role.
    """
    if ctx.is_legacy or ctx.role == "admin":
        return

    if ctx.actor_id == target_resident_id:
        return

    # If database session is available, check scoped AccessGrant
    if session:
        auth_repo = AuthRepository(session)
        has_grant = await auth_repo.check_access(
            granter_id=target_resident_id,
            grantee_id=ctx.actor_id,
            scope=scope
        )
        if has_grant:
            return

    # Check role within same household
    if ctx.household_id and ctx.role in ("family", "caregiver"):
        return

    raise TenantIsolationError(
        f"Access denied: Actor '{ctx.actor_id}' is not authorized to access "
        f"resident '{target_resident_id}' data for scope '{scope}'"
    )

