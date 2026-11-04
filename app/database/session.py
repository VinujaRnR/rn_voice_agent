"""Database session generators and transaction context managers."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import db_manager


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Asynchronous context manager yielding a scoped AsyncSession."""
    session: AsyncSession = db_manager.session_factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for injecting an async database session per request."""
    async with get_async_session() as session:
        yield session


@asynccontextmanager
async def transaction(session: AsyncSession):
    """Context manager executing a block within an atomic database transaction."""
    if session.in_transaction():
        yield session
    else:
        async with session.begin():
            yield session

