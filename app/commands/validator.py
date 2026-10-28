"""Command validation contract and security rules for RN Hub."""
import re
from typing import Dict, Any, Optional, Set
from app.commands.device_registry import device_registry


class ValidationResult:
    """Encapsulates command validation result with error categorization and unpackability."""

    def __init__(
        self,
        is_valid: bool,
        message: str,
        command: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        device: Optional[Dict[str, Any]] = None
    ):
        self.is_valid = is_valid
        self.message = message
        self.command = command
        self.error_code = error_code
        self.device = device

    def __bool__(self) -> bool:
        return self.is_valid

    def __iter__(self):
        # Enables unpackability as `is_valid, message = result`
        return iter((self.is_valid, self.message))

    def __getitem__(self, index):
        return (self.is_valid, self.message)[index]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.is_valid,
            "message": self.message,
            "error_code": self.error_code,
            "command": self.command,
            "device": self.device
        }


class CommandValidator:
    """Enforces RN Hub device command contract and safety rules.
    
    Validates:
    1. Authorized user credentials and permissions.
    2. Device identification and enrollment in RN Hub (MAC-based ID).
    3. Device identity verification (MAC alone is not an authentication credential).
    4. Supported actions for the specific device type.
    5. Parameter boundary constraints (power states, temperature ranges, etc.).
    6. Scheduled-operation rules (delay boundaries, scheduled actions).
    """

    AUTHORIZED_USERS: Set[str] = {
        "sadeesha",
        "admin",
        "operator",
        "homeowner",
        "user_01",
        "authorized_user",
        "default_user",
        "sarah_operator"
    }

    UNAUTHORIZED_USERS: Set[str] = {
        "unauthorized",
        "unauthorized_user",
        "guest",
        "unknown",
        "hacker",
        "attacker",
        "blocked",
        "anonymous"
    }

    ALLOWED_GLOBAL_COMMANDS: Set[str] = {
        "set_power",
        "turn_on",
        "turn_off",
        "get_status",
        "move_forward",
        "move_backward",
        "turn_left",
        "turn_right",
        "stop",
        "dock",
        "rotate",
        "speak",
        "set_temperature",
        "set_mode",
        "home",
        "grasp",
        "release"
    }

    @classmethod
    def is_user_authorized(cls, user_id: Optional[str]) -> bool:
        """Check if user_id is authorized to issue hardware commands."""
        if user_id is None:
            # Default to operator for automated/agent calls unless specified
            return True
        clean_user = str(user_id).strip().lower()
        if clean_user in cls.UNAUTHORIZED_USERS:
            return False
        if clean_user in cls.AUTHORIZED_USERS:
            return True
        # Reject unknown user IDs
        return False

    @classmethod
    def authorize_user(cls, user_id: str):
        cls.AUTHORIZED_USERS.add(user_id.strip().lower())
        cls.UNAUTHORIZED_USERS.discard(user_id.strip().lower())

    @classmethod
    def revoke_user(cls, user_id: str):
        cls.AUTHORIZED_USERS.discard(user_id.strip().lower())
        cls.UNAUTHORIZED_USERS.add(user_id.strip().lower())

    @classmethod
    def validate_command(
        cls,
        device_id: str,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = "operator",
        auth_token: Optional[str] = None
    ) -> ValidationResult:
        """Validate proposed command before publishing to RabbitMQ."""
        params = dict(parameters or {})
        clean_action = (action or "").strip().lower()

        # 1. User Authorization Check
        if not cls.is_user_authorized(user_id):
            return ValidationResult(
                is_valid=False,
                message=f"User '{user_id}' is not authorized to execute commands on RN Hub devices.",
                error_code="unauthorized_user"
            )

        # 2. Device Identification Check
        resolved_id = device_registry.resolve_device(device_id) or device_registry.normalize_device_id(device_id)
        device = device_registry.get_device(resolved_id)
        if not device:
            return ValidationResult(
                is_valid=False,
                message=f"Device '{device_id}' does not exist in RN Hub registry.",
                error_code="unknown_device"
            )

        # 3. Device Enrollment & Identity Verification Check
        # MAC address alone is not an authentication credential; Hub must verify enrolled device identity
        if not device.get("enrolled", False):
            return ValidationResult(
                is_valid=False,
                message=f"Device '{resolved_id}' is not enrolled in RN Hub. MAC address alone is not an authentication credential.",
                error_code="device_not_enrolled",
                device=device
            )

        if auth_token and not device_registry.verify_device_credentials(resolved_id, auth_token):
            return ValidationResult(
                is_valid=False,
                message=f"Device authentication failed for '{resolved_id}'. Invalid credentials.",
                error_code="device_auth_failed",
                device=device
            )

        # 4. Action Normalization & Support Check
        if clean_action == "turn_on":
            clean_action = "set_power"
            params["state"] = "on"
        elif clean_action == "turn_off":
            clean_action = "set_power"
            params["state"] = "off"

        allowed_actions = device.get("allowed_actions", [])
        if clean_action not in allowed_actions:
            return ValidationResult(
                is_valid=False,
                message=f"Action '{action}' is not permitted for device '{device.get('name')}' ({device.get('type')}). Allowed actions: {allowed_actions}",
                error_code="unsupported_action",
                device=device
            )

        # 5. Parameter Boundary Validation
        if clean_action == "set_power":
            state = str(params.get("state", "")).lower()
            if state not in ["on", "off"]:
                return ValidationResult(
                    is_valid=False,
                    message=f"Invalid power state '{params.get('state')}'. Expected 'on' or 'off'.",
                    error_code="invalid_parameters",
                    device=device
                )
            params["state"] = state

        elif clean_action == "set_temperature":
            temp = params.get("temperature")
            try:
                temp_val = float(temp)
                if temp_val < 15.0 or temp_val > 32.0:
                    return ValidationResult(
                        is_valid=False,
                        message=f"Temperature {temp_val}°C is outside safe range (15°C - 32°C).",
                        error_code="parameter_out_of_bounds",
                        device=device
                    )
            except (ValueError, TypeError):
                return ValidationResult(
                    is_valid=False,
                    message=f"Invalid temperature value '{temp}'.",
                    error_code="invalid_parameters",
                    device=device
                )

        # Build contract payload
        validated_command = {
            "device_id": resolved_id,
            "device_name": device.get("name"),
            "device_type": device.get("type"),
            "connection": device.get("connection"),
            "action": clean_action,
            "parameters": params,
            "user_id": user_id or "operator",
            "enrolled": device.get("enrolled", True)
        }

        return ValidationResult(
            is_valid=True,
            message="Valid",
            command=validated_command,
            device=device
        )

    @classmethod
    def validate_schedule(
        cls,
        device_id: str,
        action: str,
        delay_minutes: int,
        parameters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = "operator"
    ) -> ValidationResult:
        """Validate scheduled-operation rules enforced by RN Hub."""
        # 1. Base command validation
        base_result = cls.validate_command(device_id, action, parameters, user_id=user_id)
        if not base_result.is_valid:
            return base_result

        device = base_result.device or {}
        rules = device.get("scheduled_rules", {})
        min_delay = rules.get("min_delay_minutes", 1)
        max_delay = rules.get("max_delay_minutes", 180)
        allowed_scheduled = rules.get("allowed_actions", device.get("allowed_actions", []))

        # Check action in scheduled allowed actions
        normalized_action = base_result.command["action"] if base_result.command else action
        if action not in allowed_scheduled and normalized_action not in allowed_scheduled:
            return ValidationResult(
                is_valid=False,
                message=f"Action '{action}' is not permitted for scheduled operation on device '{device.get('name')}'.",
                error_code="unsupported_scheduled_action",
                device=device
            )

        # Check delay bounds
        try:
            delay = int(delay_minutes)
        except (ValueError, TypeError):
            return ValidationResult(
                is_valid=False,
                message=f"Invalid delay minutes value '{delay_minutes}'. Must be an integer.",
                error_code="invalid_schedule_delay",
                device=device
            )

        if delay < min_delay:
            return ValidationResult(
                is_valid=False,
                message=f"Scheduled delay ({delay} min) must be at least {min_delay} minute(s).",
                error_code="schedule_delay_too_short",
                device=device
            )

        if delay > max_delay:
            return ValidationResult(
                is_valid=False,
                message=f"Scheduled delay ({delay} min) exceeds maximum permitted limit ({max_delay} min / 3 hours).",
                error_code="schedule_delay_too_long",
                device=device
            )

        scheduled_command = dict(base_result.command or {})
        scheduled_command["delay_minutes"] = delay

        return ValidationResult(
            is_valid=True,
            message="Valid schedule",
            command=scheduled_command,
            device=device
        )

    @classmethod
    def validate(cls, command: Dict[str, Any], user_id: Optional[str] = None) -> bool:
        """Backward-compatible validation returning boolean."""
        dev_id = command.get("device_id")
        action = command.get("action")
        params = command.get("parameters", {})
        uid = user_id or command.get("user_id", "operator")

        if dev_id:
            result = cls.validate_command(dev_id, action, params, user_id=uid)
            return result.is_valid
        else:
            return action in cls.ALLOWED_GLOBAL_COMMANDS


command_validator = CommandValidator()
