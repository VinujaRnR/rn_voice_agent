"""Authentication and user session routes."""
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from app.database.session import get_db_session, transaction
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    UserMeResponse
)
from app.services.identity.user_service import UserService
from app.services.identity.household_service import HouseholdService
from app.services.identity.resident_service import ResidentService
from app.middleware.request_context import RequestContext, get_request_context
from app.middleware.authorization import require_authenticated
from app.security.auth import decode_token, create_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """Register a new user and return initial access/refresh tokens."""
    async with transaction(session):
        user, household = await UserService.register_user(
            session=session,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            role=payload.role,
            phone_number=payload.phone_number,
            household_name=payload.household_name,
            household_id=payload.household_id
        )
        token_data = await UserService.generate_user_tokens(
            session=session,
            user=user,
            household_id=household.id if household else payload.household_id
        )

    return TokenResponse(**token_data)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """Authenticate with email and password to receive JWT credentials."""
    user = await UserService.authenticate(
        session=session,
        email=payload.email,
        password=payload.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    token_data = await UserService.generate_user_tokens(
        session=session,
        user=user,
        household_id=payload.household_id
    )
    return TokenResponse(**token_data)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """Obtain a new access token using a valid refresh token."""
    try:
        decoded = decode_token(payload.refresh_token)
        if decoded.get("token_type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provided token is not a refresh token"
            )
        user_id = decoded.get("sub")
        user = await UserService.get_by_id(session, user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User inactive or not found"
            )

        token_data = await UserService.generate_user_tokens(session=session, user=user)
        return TokenResponse(**token_data)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired, please log in again"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )


@router.get("/me", response_model=UserMeResponse)
async def get_current_user_profile(
    ctx: RequestContext = Depends(require_authenticated),
    session: AsyncSession = Depends(get_db_session)
):
    """Retrieve authenticated user's profile and household memberships."""
    user = await UserService.get_by_id(session, ctx.actor_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    households = await HouseholdService.get_user_households(session, ctx.actor_id)
    profile = await ResidentService.get_profile(session, ctx.actor_id)

    hh_list = [{"id": h.id, "name": h.name, "timezone": h.timezone} for h in households]

    return UserMeResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        household_id=ctx.household_id or (households[0].id if households else None),
        households=hh_list,
        preferred_name=profile.preferred_name if profile else None
    )

