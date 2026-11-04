"""Asynchronous database connection and engine manager for MySQL 8.4."""
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncEngine,
    AsyncSession
)
from sqlalchemy import text
from app.config import settings

logger = logging.getLogger(__name__)


class DatabaseConnectionManager:
    """Manages application-lifetime SQLAlchemy async engine and session factory."""

    def __init__(self):
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._db_url: Optional[str] = None

    def initialize(self, db_url: Optional[str] = None):
        """Initialize engine and async session maker."""
        self._db_url = db_url or settings.async_database_url
        engine_kwargs = {
            "echo": False,
            "future": True,
        }

        # Apply MySQL-specific connection pool tuning if using MySQL
        if "mysql" in self._db_url:
            engine_kwargs.update({
                "pool_size": settings.mysql_pool_size,
                "max_overflow": settings.mysql_max_overflow,
                "pool_recycle": settings.mysql_pool_recycle,
                "pool_pre_ping": True,
            })
        elif "sqlite" in self._db_url:
            # SQLite does not support pool_size/max_overflow
            pass

        self._engine = create_async_engine(self._db_url, **engine_kwargs)
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False
        )
        logger.info(f"Database connection manager initialized with engine for '{self._sanitize_url(self._db_url)}'")

    def _sanitize_url(self, url: str) -> str:
        """Strip password from connection URL for safe logging."""
        if "@" in url:
            scheme_user = url.split("@")[0]
            host_db = url.split("@")[1]
            if ":" in scheme_user:
                scheme = scheme_user.split(":")[0]
                return f"{scheme}://***:***@{host_db}"
        return url

    @property
    def engine(self) -> AsyncEngine:
        """Retrieve active async engine, initializing if not already active."""
        if self._engine is None:
            self.initialize()
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Retrieve active async sessionmaker factory."""
        if self._session_factory is None:
            self.initialize()
        return self._session_factory

    async def ensure_ready(self):
        """Verify database connectivity and synchronize schema.
        Falls back to local development SQLite if MySQL server is unreachable.
        """
        from app.database.models import Base
        if self._engine is None:
            self.initialize()

        if "mysql" in (self._db_url or ""):
            try:
                async with self._engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                logger.info("MySQL 8.4 connection verified and schema synchronized.")
                return
            except Exception as exc:
                logger.warning(
                    f"MySQL 8.4 unreachable ({exc}). Falling back to local development SQLite at 'data/sarah_platform.db'."
                )
                import os
                os.makedirs("data", exist_ok=True)
                self.initialize("sqlite+aiosqlite:///data/sarah_platform.db")
                async with self._engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                logger.info("Local development SQLite schema initialized successfully.")
        else:
            import os
            os.makedirs("data", exist_ok=True)
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database schema synchronized.")

    async def check_connection(self) -> bool:
        """Verify broker database connectivity with ping query."""
        try:
            async with self.session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.warning(f"Database connectivity check failed: {e}")
            return False

    async def close(self):
        """Dispose database engine and close all connections."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database engine connections disposed.")


# Global database connection manager singleton
db_manager = DatabaseConnectionManager()

