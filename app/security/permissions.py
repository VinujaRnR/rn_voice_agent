"""Tool and device authorization permissions."""
from typing import Dict, Any, List


class PermissionManager:
    """Enforces authorization for tools, IoT devices, and robotic actuators."""

    ALLOWED_TOOLS = {
        "get_current_time",
        "get_weather",
        "search_web",
        "search_places",
        "list_devices",
        "get_device_status",
        "control_device",
        "schedule_device_action"
    }

    HAZARDOUS_DEVICES = {
        "arm_manipulator",
        "robot_base"
    }

    def is_tool_authorized(self, tool_name: str, user_role: str = "operator") -> bool:
        return tool_name in self.ALLOWED_TOOLS

    def requires_confirmation(self, device_id: str, action: str) -> bool:
        """Check if an operation involves physical motion or safety-critical hardware."""
        if device_id in self.HAZARDOUS_DEVICES:
            if action in ["move_forward", "move_backward", "home", "grasp"]:
                return True
        return False


permission_manager = PermissionManager()
