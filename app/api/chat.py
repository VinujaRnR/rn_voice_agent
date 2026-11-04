import re
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from app.gemini.client import GeminiClient
from app.gemini.schemas import GeminiResponse, DeviceCommand
from app.conversation.manager import ConversationManager
from app.stt import stt_service, whisper_service
from app.gemini.tool_agent import tool_agent
from app.commands.device_registry import device_registry
from app.tools.device_control import execute_device_command

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Singleton instances
conversation_manager = ConversationManager()
gemini_client = GeminiClient()

from app.schemas.contracts import ChatRequestContract
from app.services.chat_service import chat_service

# Link singletons so mock patches to app.api.chat.gemini_client or conversation_manager propagate
chat_service.gemini_client = gemini_client
chat_service.conversation_manager = conversation_manager


class ChatRequest(ChatRequestContract):
    session_id: Optional[str] = Field(default="default_session")
    user_id: Optional[str] = Field(default="default_user")


@router.post("", response_model=GeminiResponse)
@router.post("/", response_model=GeminiResponse)
async def chat_endpoint(request: ChatRequest):
    return await chat_service.process_chat_turn(request)



@router.post("/audio")
async def chat_audio_endpoint(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form("default_session"),
    enforce_wake_standby: Optional[bool] = Form(False)
):
    """Direct audio conversation: transcribes audio with Faster-Whisper and processes with Sarah."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded audio is empty.")

    transcript = await stt_service.transcribe(
        content,
        mime_type=file.content_type,
        filename=file.filename
    )
    if not transcript:
        return {
            "transcript": "",
            "response": GeminiResponse(
                mode="answer",
                speech="I didn't hear anything clearly. Could you please repeat that?",
                command=None,
                missing_fields=[]
            )
        }

    gemini_resp = await chat_endpoint(
        ChatRequest(
            text=transcript,
            session_id=session_id,
            enforce_wake_standby=enforce_wake_standby
        )
    )
    return {
        "transcript": transcript,
        "response": gemini_resp
    }


@router.get("/session/{session_id}/status")
async def get_session_status(session_id: str):
    """Check whether Sarah is awake and the remaining active seconds."""
    info = conversation_manager.get_session_info(session_id)
    return {
        "session_id": session_id,
        "is_awake": info["is_awake"],
        "remaining_seconds": info["remaining_seconds"]
    }


@router.post("/session/{session_id}/wake")
async def wake_session_endpoint(session_id: str):
    """Explicitly wake Sarah up."""
    conversation_manager.wake_session(session_id)
    return {"session_id": session_id, "is_awake": True, "message": "Sarah is awake and listening."}


@router.post("/session/{session_id}/sleep")
async def sleep_session_endpoint(session_id: str):
    """Explicitly put Sarah to sleep."""
    conversation_manager.sleep_session(session_id)
    return {"session_id": session_id, "is_awake": False, "message": "Sarah is now in sleep mode."}


@router.get("/history")
async def get_chat_history(session_id: str = "default_session", limit: int = 30):
    """Retrieve session dialogue history with SHA-256 cryptographic hashes."""
    messages = conversation_manager.storage.get_session_messages(session_id=session_id, limit=limit)
    return {
        "session_id": session_id,
        "count": len(messages),
        "messages": messages
    }


@router.get("/references")
async def get_chat_references(
    user_id: str = "default_user",
    limit: int = 20,
    exclude_session_id: Optional[str] = None
):
    """Retrieve user's previous conversations stored and cryptographically hashed for future references."""
    references = conversation_manager.storage.get_user_previous_conversations(
        user_id=user_id,
        limit=limit,
        exclude_session_id=exclude_session_id
    )
    return {
        "user_id": user_id,
        "count": len(references),
        "references": references
    }


@router.get("/search")
async def search_past_conversations_endpoint(
    q: str,
    user_id: str = "default_user",
    limit: int = 5
):
    """Search past conversation records by text content or SHA-256 hash."""
    results = conversation_manager.storage.search_previous_conversations(
        query=q,
        user_id=user_id,
        limit=limit
    )
    return {
        "query": q,
        "matches": results,
        "count": len(results)
    }


@router.get("/by-hash/{hash_value}")
async def get_conversation_by_hash_endpoint(hash_value: str):
    """Retrieve a specific stored conversation turn by its cryptographic SHA-256 hash."""
    record = conversation_manager.storage.get_conversation_by_hash(hash_value)
    if not record:
        raise HTTPException(status_code=404, detail="Conversation record matching hash not found.")
    return record


class ClearHistoryRequest(BaseModel):
    session_id: Optional[str] = "default_session"
    user_id: Optional[str] = "default_user"
    clear_all: Optional[bool] = False


@router.post("/clear")
@router.delete("/history")
async def clear_history_endpoint(payload: Optional[ClearHistoryRequest] = None):
    """Clear conversation messages and references from SQLite database."""
    from app.context.memory import conversation_memory
    sess = payload.session_id if payload else "default_session"
    u_id = payload.user_id if payload else "default_user"
    c_all = payload.clear_all if payload else False
    deleted = conversation_manager.storage.clear_conversation_history(
        session_id=sess,
        user_id=u_id,
        clear_all=c_all
    )
    conversation_memory.clear_memory(session_id=sess, clear_all=c_all)
    return {
        "status": "success",
        "deleted_records": deleted,
        "message": "I've cleared the entire conversation history." if c_all else "I've cleared your conversation history."
    }
