"""User, household, and resident profile repository."""
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models.identity import User, Household, HouseholdMembership, ResidentProfile
from app.database.models.personalization import UserPreference, PersonalMemory
from app.database.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository handling identity domain records."""

    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_phone(self, phone: str) -> Optional[User]:
        stmt = select(User).where(User.phone_number == phone)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_user(
        self,
        email: Optional[str] = None,
        phone_number: Optional[str] = None,
        full_name: Optional[str] = None,
        role: str = "resident",
        password_hash: Optional[str] = None
    ) -> User:
        user = User(
            email=email,
            phone_number=phone_number,
            full_name=full_name,
            role=role,
            password_hash=password_hash
        )
        return await self.create(user)

    async def create_household(
        self,
        name: str,
        timezone: str = "Australia/Sydney",
        address: Optional[str] = None,
        city: Optional[str] = None,
        country: str = "Australia"
    ) -> Household:
        household = Household(
            name=name,
            timezone=timezone,
            address=address,
            city=city,
            country=country
        )
        self.session.add(household)
        await self.session.flush()
        return household

    async def add_household_member(
        self,
        household_id: str,
        user_id: str,
        role: str = "member"
    ) -> HouseholdMembership:
        membership = HouseholdMembership(
            household_id=household_id,
            user_id=user_id,
            role=role
        )
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def get_resident_profile(self, user_id: str) -> Optional[ResidentProfile]:
        stmt = select(ResidentProfile).where(ResidentProfile.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def upsert_resident_profile(
        self,
        user_id: str,
        household_id: Optional[str] = None,
        preferred_name: Optional[str] = None,
        birth_year: Optional[int] = None,
        medical_notes: Optional[str] = None,
        emergency_contact_phone: Optional[str] = None,
        primary_language: str = "en"
    ) -> ResidentProfile:
        profile = await self.get_resident_profile(user_id)
        if profile:
            if household_id is not None:
                profile.household_id = household_id
            if preferred_name is not None:
                profile.preferred_name = preferred_name
            if birth_year is not None:
                profile.birth_year = birth_year
            if medical_notes is not None:
                profile.medical_notes = medical_notes
            if emergency_contact_phone is not None:
                profile.emergency_contact_phone = emergency_contact_phone
            if primary_language is not None:
                profile.primary_language = primary_language
            await self.session.flush()
            return profile
        else:
            profile = ResidentProfile(
                user_id=user_id,
                household_id=household_id,
                preferred_name=preferred_name,
                birth_year=birth_year,
                medical_notes=medical_notes,
                emergency_contact_phone=emergency_contact_phone,
                primary_language=primary_language
            )
            self.session.add(profile)
            await self.session.flush()
            return profile

    async def get_household_by_id(self, household_id: str) -> Optional[Household]:
        stmt = select(Household).where(Household.id == household_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_user_households(self, user_id: str) -> List[Household]:
        stmt = (
            select(Household)
            .join(HouseholdMembership, HouseholdMembership.household_id == Household.id)
            .where(HouseholdMembership.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_household_members(self, household_id: str) -> List[HouseholdMembership]:
        stmt = (
            select(HouseholdMembership)
            .where(HouseholdMembership.household_id == household_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_user_preferences(self, user_id: str) -> Optional[UserPreference]:
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def upsert_user_preferences(
        self,
        user_id: str,
        wake_word: Optional[str] = None,
        voice_name: Optional[str] = None,
        speaking_rate: Optional[float] = None,
        volume: Optional[float] = None,
        temperature_unit: Optional[str] = None
    ) -> UserPreference:
        pref = await self.get_user_preferences(user_id)
        if pref:
            if wake_word is not None:
                pref.wake_word = wake_word
            if voice_name is not None:
                pref.voice_name = voice_name
            if speaking_rate is not None:
                pref.speaking_rate = speaking_rate
            if volume is not None:
                pref.volume = volume
            if temperature_unit is not None:
                pref.temperature_unit = temperature_unit
            await self.session.flush()
            return pref
        else:
            pref = UserPreference(
                user_id=user_id,
                wake_word=wake_word or "Sarah",
                voice_name=voice_name or "en-US-JennyNeural",
                speaking_rate=speaking_rate if speaking_rate is not None else 1.0,
                volume=volume if volume is not None else 1.0,
                temperature_unit=temperature_unit or "celsius"
            )
            self.session.add(pref)
            await self.session.flush()
            return pref

    async def add_personal_memory(
        self,
        user_id: str,
        memory_key: str,
        memory_value: str,
        category: str = "general",
        importance_score: int = 5
    ) -> PersonalMemory:
        memory = PersonalMemory(
            user_id=user_id,
            memory_key=memory_key,
            memory_value=memory_value,
            category=category,
            importance_score=importance_score
        )
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def get_personal_memories(
        self,
        user_id: str,
        category: Optional[str] = None
    ) -> List[PersonalMemory]:
        stmt = select(PersonalMemory).where(PersonalMemory.user_id == user_id)
        if category:
            stmt = stmt.where(PersonalMemory.category == category)
        stmt = stmt.order_by(PersonalMemory.importance_score.desc(), PersonalMemory.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

