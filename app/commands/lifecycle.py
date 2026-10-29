"""Command lifecycle states, tracking, and speech outcome formatting for RN Hub."""
import asyncio
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime, timezone


class CommandState(str, Enum):
    """Lifecycle states of a hardware command dispatched to RN Hub."""
    VALIDATED = "validated"      # Backend verified device, actions, parameters, user permissions
    PUBLISHED = "published"      # RabbitMQ broker confirmed receipt of persistent message
    ACCEPTED = "accepted"        # RN Hub consumed command and queued it for hardware execution
    COMPLETED = "completed"      # RN Hub verified device action executed on physical hardware
    REJECTED = "rejected"        # Command rejected by validator or RN Hub safety policy
    FAILED = "failed"            # Hardware/network execution failed on device or Hub
    EXPIRED = "expired"          # Command timed out before execution could be verified
    UNKNOWN = "unknown"          # Unrecognized command ID or unresolvable state


def generate_speech_outcome(
    device_name: str,
    action: str,
    state: str,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None
) -> str:
    """Generate final spoken TTS response based on actual RN Hub execution evidence."""
    res = result or {}
    dev = device_name or "the device"

    if state == CommandState.COMPLETED.value:
        if action in ["set_power", "turn_on", "turn_off"]:
            p_state = res.get("power_state") or res.get("state") or ("on" if action == "turn_on" else "off")
            return f"The {dev} has been turned {p_state}."
        elif action == "get_status":
            st = res.get("status", "online")
            p_state = res.get("power_state", "off")
            return f"{dev} is {st} and currently turned {p_state}."
        else:
            return f"{dev} has successfully completed {action}."

    elif state == CommandState.ACCEPTED.value:
        return f"RN Hub accepted the command for {dev} and is executing."

    elif state == CommandState.REJECTED.value:
        reason = error or res.get("reason") or "Safety rules prevented execution."
        return f"Command for {dev} was rejected by RN Hub: {reason}"

    elif state == CommandState.FAILED.value:
        reason = error or res.get("error") or "Hardware execution error."
        return f"Execution failed on {dev}: {reason}"

    elif state == CommandState.EXPIRED.value:
        return f"Command execution timed out for {dev}."

    else:
        return f"Status for {dev} is currently {state}."


class CommandLifecycleTracker:
    """Coordinates command state updates and async waiting for device results."""

    def __init__(self):
        self._waiters: Dict[str, asyncio.Future] = {}

    def get_or_create_waiter(self, command_id: str) -> asyncio.Future:
        if command_id not in self._waiters or self._waiters[command_id].done():
            loop = asyncio.get_event_loop()
            self._waiters[command_id] = loop.create_future()
        return self._waiters[command_id]

    def notify_result(self, command_id: str, result_payload: Dict[str, Any]):
        waiter = self._waiters.get(command_id)
        if waiter and not waiter.done():
            waiter.set_result(result_payload)

    async def wait_for_completion(
        self,
        command_id: str,
        timeout: float = 15.0
    ) -> Optional[Dict[str, Any]]:
        waiter = self.get_or_create_waiter(command_id)
        try:
            return await asyncio.wait_for(waiter, timeout=timeout)
        except asyncio.TimeoutError:
            return None


command_tracker = CommandLifecycleTracker()
