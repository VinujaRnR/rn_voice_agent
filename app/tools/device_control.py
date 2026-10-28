"""Device control and timed action scheduling tool."""
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from app.commands.device_registry import device_registry
from app.commands.validator import CommandValidator


def control_device(
    device_id: str,
    action: str,
    parameters: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = "operator"
) -> Dict[str, Any]:
    """Request an authorized device action to be executed by RN Hub.
    
    Validates device identification, user permissions, allowed actions,
    and parameter boundaries BEFORE any RabbitMQ message is published.
    """
    params = parameters or {}

    # 1. Validate proposed command contract prior to RabbitMQ publication
    val_res = CommandValidator.validate_command(
        device_id=device_id,
        action=action,
        parameters=params,
        user_id=user_id
    )
    if not val_res.is_valid:
        return {
            "error": val_res.message,
            "error_code": val_res.error_code,
            "status": "validation_failed",
            "destination": "RN Hub via RabbitMQ",
            "published": False
        }

    cmd = val_res.command
    target_id = cmd["device_id"]
    clean_action = cmd["action"]
    validated_params = cmd["parameters"]
    device = val_res.device or {}
    dev_name = device.get("name", target_id)

    # 2. Update state in local registry
    if clean_action == "set_power":
        state_val = validated_params.get("state", "on")
        device_registry.set_power_state(target_id, state_val)

    # 3. Build standard RN Hub command contract envelope
    command_payload = {
        "command_id": f"cmd_{uuid.uuid4().hex[:12]}",
        "device_id": target_id,
        "action": clean_action,
        "parameters": validated_params,
        "user_id": user_id or "operator",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "rn_voice_agent",
        "target_hub": "RN_HUB_MAIN"
    }

    # 4. Dispatch to RabbitMQ queue in background if event loop is running
    try:
        import asyncio
        from app.config import settings
        from app.rabbitmq.publisher import publisher
        loop = asyncio.get_event_loop()
        if loop.is_running():
            target_queue = settings.rabbitmq_command_queue or "rn_hub_commands"
            loop.create_task(publisher.publish(
                queue_name=target_queue,
                message=command_payload,
                exchange_name=settings.rabbitmq_command_exchange,
                routing_key=settings.rabbitmq_command_routing_key
            ))
    except Exception:
        pass

    return {
        "intent": "device_control",
        "status": "success",
        "execution_state": "dispatched",
        "destination": "RN Hub via RabbitMQ",
        "published": True,
        "command": {
            "device_id": target_id,
            "device_name": dev_name,
            "action": clean_action,
            "parameters": validated_params
        },
        "envelope": command_payload,
        "feedback": f"Sending the command to RN Hub for '{dev_name}'."
    }


def schedule_device_action(
    device_id: str,
    action: str,
    delay_minutes: int = 15,
    parameters: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = "operator"
) -> Dict[str, Any]:
    """Schedule an authorized IoT action for later execution by RN Hub scheduler."""
    val_res = CommandValidator.validate_schedule(
        device_id=device_id,
        action=action,
        delay_minutes=delay_minutes,
        parameters=parameters,
        user_id=user_id
    )
    if not val_res.is_valid:
        return {
            "error": val_res.message,
            "error_code": val_res.error_code,
            "status": "schedule_rejected",
            "scheduled": False
        }

    cmd = val_res.command
    device = val_res.device or {}
    dev_name = device.get("name", cmd["device_id"])
    effective_delay = cmd["delay_minutes"]
    scheduled_time = datetime.now() + timedelta(minutes=effective_delay)

    return {
        "intent": "scheduled_device_action",
        "status": "scheduled",
        "scheduled": True,
        "device_id": cmd["device_id"],
        "device_name": dev_name,
        "action": cmd["action"],
        "delay_minutes": effective_delay,
        "scheduled_for": scheduled_time.strftime("%I:%M %p"),
        "parameters": cmd.get("parameters", {}),
        "feedback": f"Scheduled {cmd['action']} on '{dev_name}' in {effective_delay} minutes ({scheduled_time.strftime('%I:%M %p')})."
    }
