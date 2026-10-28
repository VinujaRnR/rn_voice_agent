from fastapi import APIRouter
from typing import List

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/")
async def list_sessions() -> List[str]:
    return []


@router.post("/new")
async def create_session():
    return {"session_id": "default-session"}
