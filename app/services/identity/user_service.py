"""User identity and lifecycle service."""
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.database.models.identity import User, Household
from app.database.repositories.user_repository import UserRepository
from app.security.auth import hash_password, verify_password, create_access_token, create_refresh_token


class UserService:
    """Service handling user accounts, credentials, and authentication."""

    @staticmethod
    async def register_user(
        session: AsyncSession,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        role: str = "resident",
        phone_number: Optional[str] = None,
        household_name: Optional[str] = None,
        household_id: Optional[str] = None
    ) -> Tuple[User, Optional[Household]]:
        """Register a new user, hash password, and set up household."""
        repo = UserRepository(session)

        # Check existing user
        existing = await repo.get_by_email(email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User with email '{email}' already exists"
            )

        hashed = hash_password(password)
        user = await repo.create_user(
            email=email,
            phone_number=phone_number,
            full_name=full_name,
            role=role,
            password_hash=hashed
        )

        household = None
        # Handle household association
        if household_id:
            household = await repo.get_household_by_id(household_id)
            if household:
                await repo.add_household_member(
                    household_id=household.id,
                    user_id=user.id,
                    role="member" if role != "admin" else "owner"
                )
        elif household_name:
            household = await repo.create_household(
                name=household_name
            )
            await repo.add_household_member(
                household_id=household.id,
                user_id=user.id,
                role="owner"
            )

        # Create default resident profile if role is resident
        if role == "resident":
            await repo.upsert_resident_profile(
                user_id=user.id,
                household_id=household.id if household else None,
                preferred_name=full_name or email.split("@")[0]
            )

        # Initialize default preferences
        await repo.upsert_user_preferences(user_id=user.id)

        return user, household

    @staticmethod
    async def authenticate(
        session: AsyncSession,
        email: str,
        password: str
    ) -> Optional[User]:
        """Authenticate user against password hash."""
        repo = UserRepository(session)
        user = await repo.get_by_email(email)
        if not user or not user.password_hash:
            return None
        if not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: str) -> Optional[User]:
        repo = UserRepository(session)
        return await repo.get_by_id(user_id)

    @staticmethod
    async def get_by_email(session: AsyncSession, email: str) -> Optional[User]:
        repo = UserRepository(session)
        return await repo.get_by_email(email)

    @staticmethod
    async def generate_user_tokens(
        session: AsyncSession,
        user: User,
        household_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate JWT access and refresh tokens for authenticated user."""
        repo = UserRepository(session)
        if not household_id:
            households = await repo.get_user_households(user.id)
            if households:
                household_id = households[0].id

        claims = {
            "email": user.email,
            "role": user.role,
            "household_id": household_id,
            "name": user.full_name
        }

        access_token = create_access_token(subject=user.id, claims=claims)
        refresh_token = create_refresh_token(subject=user.id, claims={"role": user.role})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": user.id,
            "role": user.role,
            "household_id": household_id
        }

