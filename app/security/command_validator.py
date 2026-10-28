"""Independent command validator for IoT and robotic hardware."""
from typing import Dict, Any, Tuple, Optional
from app.commands.validator import CommandValidator


class CommandSafetyValidator:
    """Validates device identity, allowed actions, and safe parameter boundaries."""

    @classmethod
    def validate_command(
        cls,
        device_id: str,
        action: str,
        parameters: Dict[str, Any],
        user_id: Optional[str] = "operator"
    ) -> Tuple[bool, str]:
        res = CommandValidator.validate_command(
            device_id=device_id,
            action=action,
            parameters=parameters,
            user_id=user_id
        )
        return res.is_valid, res.message


command_safety_validator = CommandSafetyValidator()
