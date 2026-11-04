"""Device service handling IoT device command validation, resolution, and dispatch."""
from typing import Optional, Dict, Any
from app.tools.device_control import control_device, schedule_device_action, get_device_topics
from app.commands.device_registry import device_registry
from app.schemas.contracts import DeviceControlRequestContract, DeviceControlResponseContract


class DeviceService:
    """Service mediating device operations between API/Agent and IoT transport."""

    def __init__(self, registry=None):
        self.registry = registry or device_registry

    def resolve_device(self, identifier: str) -> Optional[str]:
        """Resolve device name or alias to primary hardware/hub identifier."""
        return self.registry.resolve_device(identifier) or self.registry.normalize_device_id(identifier)

    def execute_command(
        self,
        request: DeviceControlRequestContract,
        command_obj: Optional[Any] = None
    ) -> DeviceControlResponseContract:
        """Validate and dispatch a device command to RN Hub transport."""
        res = control_device(
            device_id=request.device_id,
            action=request.action,
            parameters=request.parameters,
            user_id=request.user_id,
            session_id=request.session_id or "default_session",
            command_obj=command_obj
        )
        return DeviceControlResponseContract(
            status=res.get("status", "unknown"),
            command_id=res.get("command_id"),
            destination=res.get("destination", "RN Hub via RabbitMQ"),
            published=bool(res.get("published", False)),
            feedback=res.get("feedback") or res.get("error") or "Command processed."
        )

    def schedule_action(
        self,
        device_id: str,
        action: str,
        delay_minutes: int = 15,
        parameters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = "operator",
        session_id: str = "default_session"
    ) -> Dict[str, Any]:
        """Schedule timed device action."""
        return schedule_device_action(
            device_id=device_id,
            action=action,
            delay_minutes=delay_minutes,
            parameters=parameters,
            user_id=user_id,
            session_id=session_id
        )


# Global singleton instance
device_service = DeviceService()

