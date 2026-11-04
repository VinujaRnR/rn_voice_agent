"""Base generic repository for SQLAlchemy async models."""
from typing import Generic, TypeVar, Type, Optional, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.database.base import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Generic base repository providing CRUD and transaction capabilities."""

    def __init__(self, model_class: Type[T], session: AsyncSession):
        self.model_class = model_class
        self.session = session

    async def get_by_id(self, entity_id: Any) -> Optional[T]:
        """Fetch entity by primary key."""
        return await self.session.get(self.model_class, entity_id)

    async def list_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """List entities with pagination."""
        stmt = select(self.model_class).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, entity: T) -> T:
        """Add new entity to session."""
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity: T) -> T:
        """Merge entity and flush changes."""
        merged = await self.session.merge(entity)
        await self.session.flush()
        return merged

    async def delete(self, entity: T) -> None:
        """Delete entity from session."""
        await self.session.delete(entity)
        await self.session.flush()

    async def delete_by_id(self, entity_id: Any) -> bool:
        """Delete entity by primary key."""
        entity = await self.get_by_id(entity_id)
        if entity:
            await self.delete(entity)
            return True
        return False

    async def commit(self) -> None:
        """Commit current transaction."""
        await self.session.commit()

    async def rollback(self) -> None:
        """Roll back current transaction."""
        await self.session.rollback()

