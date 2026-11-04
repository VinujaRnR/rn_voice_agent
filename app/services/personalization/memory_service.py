"""Resident personal memory and conversational context service."""
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.database.models.personalization import PersonalMemory
from app.database.repositories.user_repository import UserRepository
from app.middleware.request_context import RequestContext
from app.middleware.tenant_isolation import enforce_resident_access


class PersonalizationMemoryService:
    """Service handling encrypted personal memories for resident personalization."""

    @classmethod
    async def get_authorized_memories(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        target_resident_id: str,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve decrypted resident personal memories after verifying authorization."""
        await enforce_resident_access(ctx, target_resident_id, scope="profile:read", session=session)
        repo = UserRepository(session)
        memories = await repo.get_personal_memories(user_id=target_resident_id, category=category)
        return [
            {
                "id": m.id,
                "user_id": m.user_id,
                "memory_key": m.memory_key,
                "memory_value": m.memory_value,
                "category": m.category,
                "importance_score": m.importance_score,
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in memories
        ]

    @classmethod
    async def save_personal_memory(
        cls,
        session: AsyncSession,
        ctx: RequestContext,
        target_resident_id: str,
        memory_key: str,
        memory_value: str,
        category: str = "general",
        importance_score: int = 5
    ) -> Dict[str, Any]:
        """Save a new encrypted personal memory for the resident."""
        await enforce_resident_access(ctx, target_resident_id, scope="profile:write", session=session)
        repo = UserRepository(session)
        mem = await repo.add_personal_memory(
            user_id=target_resident_id,
            memory_key=memory_key,
            memory_value=memory_value,
            category=category,
            importance_score=importance_score
        )
        return {
            "id": mem.id,
            "user_id": mem.user_id,
            "memory_key": mem.memory_key,
            "memory_value": mem.memory_value,
            "category": mem.category,
            "importance_score": mem.importance_score,
            "created_at": mem.created_at.isoformat() if mem.created_at else None
        }

