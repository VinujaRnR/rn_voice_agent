"""Tool authorization, tenant boundaries, and safety policies."""
from typing import Dict, Any, Optional, Tuple
from app.middleware.request_context import RequestContext
from app.security.permissions import permission_manager
from app.security.command_validator import command_safety_validator


# Permission requirements per tool name
TOOL_PERMISSION_MAP: Dict[str, str] = {
    "get_current_time": "conversation:read",
    "get_weather": "conversation:read",
    "search_web": "conversation:read",
    "search_places": "conversation:read",
    "list_devices": "device:read",
    "get_device_status": "device:read",
    "control_device": "device:control",
    "schedule_device_action": "device:control",
    "set_reminder": "reminder:write",
    "list_reminders": "reminder:read",
    "cancel_reminder": "reminder:cancel",
    "search_past_conversations": "conversation:read",
    # Steps 11-15 tools
    "manage_family_contacts": "profile:read",
    "check_medication_schedule": "profile:read",
    "check_safety_status": "profile:read",
    "find_local_services": "conversation:read",
    "control_music": "device:control",
    "play_music": "device:control"
}

# Hazardous devices requiring safety confirmation
CONFIRMATION_REQUIRED_DEVICES = {"arm_manipulator", "robot_base", "smart_door_lock"}


class ToolAuthorizationManager:
    """Validates authorization, household bounds, and hardware safety before tool execution."""

    @classmethod
    def check_authorization(
        cls,
        tool_name: str,
        context: RequestContext,
        arguments: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Check if context holds permission to execute tool."""
        # 1. Permission check
        required_perm = TOOL_PERMISSION_MAP.get(tool_name)
        if required_perm and not context.has_permission(required_perm):
            return False, f"Access denied: Missing required permission '{required_perm}' for tool '{tool_name}'"

        # 2. Device safety and confirmation checks
        if tool_name in ("control_device", "schedule_device_action"):
            dev_id = arguments.get("device_id", "")
            action = arguments.get("action", "")
            params = arguments.get("parameters", {})

            # Safety validator check
            is_safe, safety_msg = command_safety_validator.validate_command(
                device_id=dev_id,
                action=action,
                parameters=params,
                user_id=context.actor_id
            )
            if not is_safe:
                return False, f"Safety check failed: {safety_msg}"

            # Hazardous confirmation check
            if dev_id in CONFIRMATION_REQUIRED_DEVICES:
                if action in ["move_forward", "move_backward", "home", "grasp", "unlock"]:
                    return False, f"Confirmation required before executing hazardous action '{action}' on device '{dev_id}'"

        return True, "Authorized"
