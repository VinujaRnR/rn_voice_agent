"""Tests for Step 3: Multi-User Authentication, Identity, JWT, and Tenant Isolation."""
import pytest
from datetime import timedelta
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from fastapi import HTTPException

from app.database.models import Base
from app.database.session import get_db_session
from app.database.connection import db_manager
from app.security.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token
)
from app.middleware.request_context import (
    RequestContext,
    get_request_context,
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
from app.services.identity.user_service import UserService
from app.services.identity.household_service import HouseholdService
from app.services.identity.resident_service import ResidentService
from app.services.identity.membership_service import MembershipService
from app.database.repositories.auth_repository import AuthRepository
from app.main import app


@pytest.fixture
async def async_test_session():
    """Create in-memory async SQLite database engine and yield isolated session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


# =========================================================================
# 1. Password Hashing and JWT Unit Tests
# =========================================================================

def test_password_hashing():
    pwd = "ElderCareSecure2026!"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert hashed.startswith("$2b$")
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrong_pwd", hashed) is False
    assert verify_password("", hashed) is False


def test_jwt_token_creation_and_decoding():
    user_id = "user-12345"
    token = create_access_token(
        subject=user_id,
        claims={"role": "resident", "household_id": "hh-789", "email": "elizabeth@example.com"}
    )
    decoded = decode_token(token)
    assert decoded["sub"] == user_id
    assert decoded["role"] == "resident"
    assert decoded["household_id"] == "hh-789"
    assert decoded["email"] == "elizabeth@example.com"
    assert decoded["token_type"] == "access"


def test_jwt_token_expiration():
    token = create_access_token(
        subject="user-expired",
        expires_delta=timedelta(seconds=-10)
    )
    with pytest.raises(Exception):
        decode_token(token)


# =========================================================================
# 2. Identity Services Tests
# =========================================================================

@pytest.mark.asyncio
async def test_user_registration_and_authentication(async_test_session: AsyncSession):
    session = async_test_session

    # Register new resident with new household
    user, household = await UserService.register_user(
        session=session,
        email="margaret@example.com",
        password="password123",
        full_name="Margaret Thatcher",
        role="resident",
        household_name="Sunny Retirement Villa"
    )
    await session.commit()

    assert user.id is not None
    assert user.email == "margaret@example.com"
    assert household is not None
    assert household.name == "Sunny Retirement Villa"

    # Authenticate successfully
    authed_user = await UserService.authenticate(
        session=session,
        email="margaret@example.com",
        password="password123"
    )
    assert authed_user is not None
    assert authed_user.id == user.id

    # Authenticate wrong password
    failed_user = await UserService.authenticate(
        session=session,
        email="margaret@example.com",
        password="badpassword"
    )
    assert failed_user is None

    # Duplicate registration should raise 409 Conflict
    with pytest.raises(HTTPException) as exc_info:
        await UserService.register_user(
            session=session,
            email="margaret@example.com",
            password="anotherpassword"
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_household_and_membership_services(async_test_session: AsyncSession):
    session = async_test_session

    user, _ = await UserService.register_user(
        session=session,
        email="caregiver.john@example.com",
        password="password123",
        full_name="John Doe",
        role="caregiver"
    )
    hh = await HouseholdService.create_household(
        session=session,
        creator_user_id=user.id,
        name="Oak Grove Residence",
        city="Melbourne"
    )
    await session.commit()

    assert hh.id is not None
    assert hh.city == "Melbourne"

    # Verify user's households
    user_hhs = await HouseholdService.get_user_households(session, user.id)
    assert len(user_hhs) == 1
    assert user_hhs[0].id == hh.id

    # Add second user as member
    user2, _ = await UserService.register_user(
        session=session,
        email="resident.mary@example.com",
        password="password123",
        role="resident"
    )
    membership = await HouseholdService.add_member(
        session=session,
        household_id=hh.id,
        user_id=user2.id,
        role="resident"
    )
    await session.commit()
    assert membership.role == "resident"

    members = await HouseholdService.list_members(session, hh.id)
    assert len(members) == 2


# =========================================================================
# 3. Tenant Isolation & Resident Boundary Tests
# =========================================================================

def test_tenant_isolation_enforcement():
    # Context belonging to Household A
    ctx_hh_a = RequestContext(
        actor_id="user-a",
        household_id="hh-alpha",
        role="resident",
        is_authenticated=True,
        is_legacy=False
    )

    # Accessing resource in same household A -> Allowed
    enforce_household_isolation(ctx_hh_a, "hh-alpha")

    # Accessing resource in household B -> Blocked with TenantIsolationError
    with pytest.raises(TenantIsolationError) as exc_info:
        enforce_household_isolation(ctx_hh_a, "hh-beta")
    assert "Tenant boundary violation" in str(exc_info.value.detail)

    # Legacy context bypasses isolation
    legacy_ctx = RequestContext(
        actor_id="legacy-user",
        household_id=None,
        role="resident",
        is_authenticated=False,
        is_legacy=True
    )
    enforce_household_isolation(legacy_ctx, "hh-beta")

    # Admin context bypasses isolation
    admin_ctx = RequestContext(
        actor_id="admin-user",
        household_id="hh-admin",
        role="admin",
        is_authenticated=True,
        is_legacy=False
    )
    enforce_household_isolation(admin_ctx, "hh-beta")


@pytest.mark.asyncio
async def test_resident_scoped_access_and_grants(async_test_session: AsyncSession):
    session = async_test_session

    res_user, _ = await UserService.register_user(
        session=session,
        email="elder.arthur@example.com",
        password="password123",
        role="resident"
    )
    fam_user, _ = await UserService.register_user(
        session=session,
        email="daughter.claire@example.com",
        password="password123",
        role="family"
    )
    stranger_user, _ = await UserService.register_user(
        session=session,
        email="stranger@example.com",
        password="password123",
        role="resident"
    )
    await session.commit()

    # Resident accessing own data
    res_ctx = RequestContext(actor_id=res_user.id, role="resident", is_authenticated=True, is_legacy=False)
    await enforce_resident_access(res_ctx, res_user.id, scope="profile:read", session=session)

    # Stranger accessing Arthur's data -> Denied
    stranger_ctx = RequestContext(actor_id=stranger_user.id, role="resident", is_authenticated=True, is_legacy=False)
    with pytest.raises(TenantIsolationError):
        await enforce_resident_access(stranger_ctx, res_user.id, scope="profile:read", session=session)

    # Arthur grants explicit access to Claire
    auth_repo = AuthRepository(session)
    await auth_repo.grant_access(
        granter_id=res_user.id,
        grantee_id=fam_user.id,
        scope="profile:read"
    )
    await session.commit()

    claire_ctx = RequestContext(actor_id=fam_user.id, role="family", is_authenticated=True, is_legacy=False)
    # Now Claire has access under scope "profile:read"
    await enforce_resident_access(claire_ctx, res_user.id, scope="profile:read", session=session)

    # Claire does NOT have access under scope "medical:write"
    with pytest.raises(TenantIsolationError):
        await enforce_resident_access(claire_ctx, res_user.id, scope="medical:write", session=session)


# =========================================================================
# 4. RequestContext & Legacy Backward Compatibility Tests
# =========================================================================

@pytest.mark.asyncio
async def test_request_context_bearer_token_resolution():
    token = create_access_token(
        subject="user-uuid-999",
        claims={"role": "caregiver", "household_id": "hh-777", "email": "care@example.com"}
    )

    # Simulated Request with Bearer Token
    class DummyRequest:
        headers = {"Authorization": f"Bearer {token}"}

    ctx = await get_request_context(
        request=DummyRequest(),
        authorization=f"Bearer {token}",
        x_session_id=None,
        x_household_id=None,
        x_resident_id=None
    )

    assert ctx.is_authenticated is True
    assert ctx.is_legacy is False
    assert ctx.actor_id == "user-uuid-999"
    assert ctx.role == "caregiver"
    assert ctx.household_id == "hh-777"
    assert ctx.email == "care@example.com"
    assert ctx.has_permission("device:control") is True


@pytest.mark.asyncio
async def test_request_context_legacy_fallback():
    class DummyRequest:
        headers = {}

    ctx = await get_request_context(
        request=DummyRequest(),
        authorization=None,
        x_session_id="custom_sess_1",
        x_household_id=None,
        x_resident_id=None
    )

    assert ctx.is_authenticated is False
    assert ctx.is_legacy is True
    assert ctx.actor_id == "default_user"
    assert ctx.session_id == "custom_sess_1"
    assert ctx.role == "resident"


# =========================================================================
# 5. FastApi Auth Route Integration Tests
# =========================================================================

@pytest.mark.asyncio
async def test_auth_api_flow():
    # Setup test DB engine for FastAPI dependency override
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Register new account
            reg_resp = await client.post("/api/v1/auth/register", json={
                "email": "betty.white@example.com",
                "password": "SecurePassword99!",
                "full_name": "Betty White",
                "role": "resident",
                "household_name": "Palm Springs Cottage"
            })
            assert reg_resp.status_code == 201, reg_resp.text
            reg_data = reg_resp.json()
            assert "access_token" in reg_data
            assert "refresh_token" in reg_data
            assert reg_data["role"] == "resident"
            access_token = reg_data["access_token"]
            refresh_token = reg_data["refresh_token"]

            # 2. Access /me with Bearer token
            me_resp = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            assert me_resp.status_code == 200, me_resp.text
            me_data = me_resp.json()
            assert me_data["email"] == "betty.white@example.com"
            assert me_data["role"] == "resident"
            assert len(me_data["households"]) == 1

            # 3. Access /me without Bearer token -> 401 Unauthorized
            unauth_resp = await client.get("/api/v1/auth/me")
            assert unauth_resp.status_code == 401

            # 4. Login with correct credentials
            login_resp = await client.post("/api/v1/auth/login", json={
                "email": "betty.white@example.com",
                "password": "SecurePassword99!"
            })
            assert login_resp.status_code == 200
            assert "access_token" in login_resp.json()

            # 5. Refresh token
            ref_resp = await client.post("/api/v1/auth/refresh", json={
                "refresh_token": refresh_token
            })
            assert ref_resp.status_code == 200
            assert "access_token" in ref_resp.json()

    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await engine.dispose()

