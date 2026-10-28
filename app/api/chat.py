from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from app.gemini.client import GeminiClient
from app.gemini.schemas import GeminiResponse, DeviceCommand
from app.conversation.manager import ConversationManager
from app.stt import stt_service, whisper_service
from app.gemini.tool_agent import tool_agent
from app.commands.device_registry import device_registry

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Singleton instances
conversation_manager = ConversationManager()
gemini_client = GeminiClient()


class ChatRequest(BaseModel):
    text: Optional[str] = None
    message: Optional[str] = None
    session_id: Optional[str] = Field(default="default_session")
    enforce_wake_standby: Optional[bool] = False

    def get_query(self) -> str:
        return (self.text or self.message or "").strip()


@router.post("", response_model=GeminiResponse)
@router.post("/", response_model=GeminiResponse)
async def chat_endpoint(request: ChatRequest):
    user_query = request.get_query()
    session_id = request.session_id or "default_session"

    if not user_query:
        return GeminiResponse(
            mode="answer",
            speech="I did not catch that. Please speak or type your request again.",
            command=None,
            missing_fields=[]
        )

    # 1. Fetch conversation history for this session
    history = conversation_manager.get_history(session_id)

    # 2. Record user query in SQLite database
    conversation_manager.add_user_message(session_id, user_query)

    # 3. Check for multi-turn clarification resolution with intent preservation and wake status
    local_resolution = conversation_manager.resolve_intent_with_context(
        session_id,
        user_query,
        enforce_wake_standby=request.enforce_wake_standby or False
    )
    if local_resolution:
        gemini_response = local_resolution
    elif tool_agent.needs_tools(user_query):
        gemini_response = await tool_agent.run(user_query, session_id)
    else:
        # Build prompt incorporating previous request, question, and answer
        prompt = conversation_manager.build_clarification_prompt(session_id, user_query)

        # Request completion from Gemini
        gemini_response = await gemini_client.generate_response(
            prompt=prompt,
            conversation_history=history
        )

    # Update pending actions based on Gemini response
    if gemini_response.mode == "clarify":
        action = "set_power" if "light" in user_query.lower() else "unknown"
        state = "off" if "off" in user_query.lower() else "on"
        conversation_manager.save_pending_action(
            session_id=session_id,
            action=action,
            parameters={"state": state},
            missing_fields=gemini_response.missing_fields or ["device_id"]
        )
    elif gemini_response.mode == "device_command":
        if gemini_response.is_executable():
            # Update device state in registry
            if gemini_response.command.action in ["set_power", "turn_on", "turn_off"]:
                state = gemini_response.command.parameters.get("state", "on" if gemini_response.command.action == "turn_on" else "off")
                device_registry.set_power_state(gemini_response.command.device_id, state)
            conversation_manager.resolve_pending_action(session_id)
            conversation_manager.record_executed_command(
                session_id=session_id,
                action=gemini_response.command.action,
                target_device=gemini_response.command.device_id,
                state="sent",
                result={"destination": "RN Hub"}
            )
        else:
            # Invalid response guard
            gemini_response = GeminiResponse(
                mode="clarify",
                speech="Command could not be verified. Please specify the target device.",
                command=None,
                missing_fields=["device_id"]
            )

    # 4. Record assistant reply in SQLite message history
    assistant_text = gemini_response.speech or (
        f"Sending the command to RN Hub for device {gemini_response.command.device_id}."
        if gemini_response.command else "Command accepted."
    )
    conversation_manager.add_assistant_message(session_id, assistant_text)

    return gemini_response


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
