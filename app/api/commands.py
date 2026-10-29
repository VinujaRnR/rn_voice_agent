"""API endpoints for querying and tracking command lifecycle execution states."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any
from app.conversation.storage import ConversationStorage
from app.commands.lifecycle import CommandState, generate_speech_outcome, command_tracker
from app.commands.device_registry import device_registry

router = APIRouter(prefix="/api/commands", tags=["commands"])
storage = ConversationStorage()


@router.get("/{command_id}")
async def get_command_status(
    command_id: str,
    wait: bool = Query(default=False, description="Wait for execution result if currently pending/published"),
    timeout: float = Query(default=3.0, description="Max seconds to wait if wait=True")
):
    """Retrieve command execution status and speech outcome."""
    record = storage.get_command(command_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Command '{command_id}' not found.")

    current_state = record.get("state", "unknown")

    # If wait is requested and command is not in a terminal state
    if wait and current_state in [CommandState.VALIDATED.value, CommandState.PUBLISHED.value, CommandState.ACCEPTED.value]:
        completed_data = await command_tracker.wait_for_completion(command_id, timeout=timeout)
        if completed_data:
            record = storage.get_command(command_id) or record
            current_state = record.get("state", "unknown")

    device_id = record.get("target_device")
    dev_info = device_registry.get_device(device_id) if device_id else None
    dev_name = dev_info.get("name") if dev_info else (device_id or "the device")

    speech_outcome = generate_speech_outcome(
        device_name=dev_name,
        action=record.get("action", "set_power"),
        state=current_state,
        result=record.get("result"),
        error=record.get("error")
    )

    return {
        "command_id": command_id,
        "session_id": record.get("session_id"),
        "device_id": device_id,
        "device_name": dev_name,
        "action": record.get("action"),
        "state": current_state,
        "parameters": record.get("parameters", {}),
        "result": record.get("result", {}),
        "error": record.get("error"),
        "speech_outcome": speech_outcome,
        "timestamp": record.get("timestamp"),
        "updated_at": record.get("updated_at")
    }
