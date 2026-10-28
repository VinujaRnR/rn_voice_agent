"""Step 10 Tests — RN Hub device registry and command contract validation."""
import pytest
from unittest.mock import patch, AsyncMock
from app.commands.device_registry import (
    device_registry,
    normalize_device_id,
    is_mac_format,
    format_mac_address,
)
from app.commands.validator import CommandValidator, ValidationResult
from app.tools.device_control import control_device, schedule_device_action
from app.tools.device_status import get_device_status


def test_device_registry_fields_and_relay_spec():
    """Verify that RN Hub device registry contains the required fields for the lighting relay.
    
    Required specification:
    - Device ID: 98a316e6b658
    - Device name: Testing Farm Lights
    - Device type: Relay
    - Connection: USB-connected ESP8266
    - Allowed actions: set_power, get_status (and turn_on, turn_off)
    - Online status: Reported by RN Hub
    """
    dev = device_registry.get_device("98a316e6b658")
    assert dev is not None
    assert dev["id"] == "98a316e6b658"
    assert dev["name"] == "Testing Farm Lights"
    assert dev["type"] == "Relay"
    assert dev["connection"] == "USB-connected ESP8266"
    assert "set_power" in dev["allowed_actions"]
    assert "get_status" in dev["allowed_actions"]
    assert "status" in dev and dev["status"] == "online"
    assert "Reported by RN Hub" in dev["online_status"]


def test_mac_based_format_identification_and_normalization():
    """Verify device identification using registered MAC-based formats."""
    # Test canonical 12-char hex format
    assert is_mac_format("98a316e6b658") is True
    assert normalize_device_id("98a316e6b658") == "98a316e6b658"

    # Test colon-delimited MAC format
    assert is_mac_format("98:a3:16:e6:b6:58") is True
    assert normalize_device_id("98:a3:16:e6:b6:58") == "98a316e6b658"
    assert format_mac_address("98a316e6b658") == "98:a3:16:e6:b6:58"

    # Test hyphen-delimited and uppercase format
    assert normalize_device_id("98-A3-16-E6-B6-58") == "98a316e6b658"

    # Registry lookups should succeed regardless of MAC representation
    dev1 = device_registry.get_device("98a316e6b658")
    dev2 = device_registry.get_device("98:a3:16:e6:b6:58")
    dev3 = device_registry.get_device("98-a3-16-e6-b6-58")
    assert dev1 is not None
    assert dev2 is not None
    assert dev3 is not None
    assert dev1["name"] == dev2["name"] == dev3["name"] == "Testing Farm Lights"


def test_mac_alone_is_not_authentication_credential():
    """Verify that MAC address alone is not sufficient; device identity and enrollment must be verified."""
    # 1. Enrolled device with credentials on record
    assert device_registry.is_device_enrolled("98a316e6b658") is True
    assert device_registry.verify_device_credentials("98a316e6b658") is True

    # Valid token verification
    assert device_registry.verify_device_credentials("98a316e6b658", "esp_token_98a316e6b658") is True
    # Invalid token verification fails
    assert device_registry.verify_device_credentials("98a316e6b658", "wrong_forged_token") is False

    # 2. Fabricated / Unenrolled MAC address must be rejected
    unenrolled_mac = "112233445566"
    assert is_mac_format(unenrolled_mac) is True  # Valid MAC format
    assert device_registry.get_device(unenrolled_mac) is None
    assert device_registry.is_device_enrolled(unenrolled_mac) is False
    assert device_registry.verify_device_credentials(unenrolled_mac) is False

    # Validation must reject unenrolled MAC
    res = CommandValidator.validate_command(
        device_id=unenrolled_mac,
        action="set_power",
        parameters={"state": "on"}
    )
    assert res.is_valid is False
    assert res.error_code == "unknown_device" or res.error_code == "device_not_enrolled"


def test_validator_rejects_unauthorized_users():
    """Verify that command validator rejects unauthorized or unknown users."""
    # Authorized users
    for user in ["sadeesha", "admin", "operator", "homeowner", "user_01"]:
        res = CommandValidator.validate_command(
            device_id="98a316e6b658",
            action="set_power",
            parameters={"state": "on"},
            user_id=user
        )
        assert res.is_valid is True

    # Unauthorized / blocked users
    for user in ["unauthorized", "hacker", "guest", "unknown_intruder", "blocked"]:
        res = CommandValidator.validate_command(
            device_id="98a316e6b658",
            action="set_power",
            parameters={"state": "on"},
            user_id=user
        )
        assert res.is_valid is False
        assert res.error_code == "unauthorized_user"
        assert "not authorized" in res.message


def test_validator_rejects_unsupported_actions_for_relay():
    """Verify that lighting relay rejects unsupported actions (e.g. robotic motion)."""
    # Relay supports set_power, get_status, turn_on, turn_off
    valid_power = CommandValidator.validate_command(
        device_id="98a316e6b658",
        action="set_power",
        parameters={"state": "on"}
    )
    assert valid_power.is_valid is True

    valid_status = CommandValidator.validate_command(
        device_id="98a316e6b658",
        action="get_status"
    )
    assert valid_status.is_valid is True

    # Motion commands must be rejected on Relay
    invalid_motion = CommandValidator.validate_command(
        device_id="98a316e6b658",
        action="move_forward",
        parameters={"distance": 1.0}
    )
    assert invalid_motion.is_valid is False
    assert invalid_motion.error_code == "unsupported_action"
    assert "not permitted" in invalid_motion.message


def test_validator_rejects_invalid_parameters():
    """Verify that invalid power parameters (not 'on'/'off') are rejected."""
    # Missing/invalid states
    for bad_state in ["explode", "maybe", "123", "", None]:
        res = CommandValidator.validate_command(
            device_id="98a316e6b658",
            action="set_power",
            parameters={"state": bad_state}
        )
        assert res.is_valid is False
        assert res.error_code == "invalid_parameters"
        assert "Invalid power state" in res.message


def test_scheduled_operation_rules_for_lighting_relay():
    """Verify RN Hub scheduled-operation rules for lighting relay.
    
    Rules:
    - Min delay: 1 minute (reject 0 or negative delays)
    - Max delay: 180 minutes (reject > 3 hours)
    - Allowed scheduled actions: set_power, turn_on, turn_off
    """
    # Valid schedule
    valid_sch = CommandValidator.validate_schedule(
        device_id="98a316e6b658",
        action="turn_off",
        delay_minutes=30,
        user_id="operator"
    )
    assert valid_sch.is_valid is True
    assert valid_sch.command["delay_minutes"] == 30

    # Upper boundary: 180 min is valid
    max_boundary = CommandValidator.validate_schedule(
        device_id="98a316e6b658",
        action="turn_off",
        delay_minutes=180,
        user_id="operator"
    )
    assert max_boundary.is_valid is True

    # Exceeding upper boundary (e.g. 240 minutes) must be rejected
    too_long = CommandValidator.validate_schedule(
        device_id="98a316e6b658",
        action="turn_off",
        delay_minutes=240,
        user_id="operator"
    )
    assert too_long.is_valid is False
    assert too_long.error_code == "schedule_delay_too_long"
    assert "exceeds maximum permitted limit" in too_long.message

    # Non-positive delays (0 or negative) must be rejected
    for bad_delay in [0, -10]:
        too_short = CommandValidator.validate_schedule(
            device_id="98a316e6b658",
            action="turn_off",
            delay_minutes=bad_delay,
            user_id="operator"
        )
        assert too_short.is_valid is False
        assert too_short.error_code == "schedule_delay_too_short"
        assert "must be at least 1 minute" in too_short.message

    # Unsupported action for scheduling on relay
    unsupported_sch = CommandValidator.validate_schedule(
        device_id="98a316e6b658",
        action="dock",
        delay_minutes=15,
        user_id="operator"
    )
    assert unsupported_sch.is_valid is False


@pytest.mark.asyncio
async def test_pass_condition_validation_before_rabbitmq_publish():
    """Pass condition: The backend can identify a device and validate a proposed
    command before any RabbitMQ message is published.
    
    If validation fails:
    - No RabbitMQ message is published.
    - Error is returned with status 'validation_failed'.
    
    If validation passes:
    - Proposed command envelope is constructed with all contract fields.
    """
    with patch("app.rabbitmq.publisher.publisher.publish", new_callable=AsyncMock) as mock_pub:
        # Case 1: Invalid parameters -> REJECT BEFORE PUBLISH
        res_invalid = control_device(
            device_id="98a316e6b658",
            action="set_power",
            parameters={"state": "invalid_mode"},
            user_id="operator"
        )
        assert res_invalid["status"] == "validation_failed"
        assert res_invalid["published"] is False
        # RabbitMQ publisher must NOT have been called
        mock_pub.assert_not_called()

        # Case 2: Unauthorized user -> REJECT BEFORE PUBLISH
        res_unauth = control_device(
            device_id="98a316e6b658",
            action="set_power",
            parameters={"state": "on"},
            user_id="hacker_unauthorized"
        )
        assert res_unauth["status"] == "validation_failed"
        assert res_unauth["error_code"] == "unauthorized_user"
        assert res_unauth["published"] is False
        mock_pub.assert_not_called()

        # Case 3: Unknown device -> REJECT BEFORE PUBLISH
        res_unknown = control_device(
            device_id="unknown_device_999",
            action="set_power",
            parameters={"state": "on"},
            user_id="operator"
        )
        assert res_unknown["status"] == "validation_failed"
        assert res_unknown["published"] is False
        mock_pub.assert_not_called()

        # Case 4: Valid command -> VALIDATED AND DISPATCHED
        res_valid = control_device(
            device_id="98:a3:16:e6:b6:58",  # Colon MAC format
            action="set_power",
            parameters={"state": "on"},
            user_id="sadeesha"
        )
        assert res_valid["status"] == "success"
        assert res_valid["published"] is True
        assert "envelope" in res_valid

        envelope = res_valid["envelope"]
        assert envelope["device_id"] == "98a316e6b658"
        assert envelope["action"] == "set_power"
        assert envelope["parameters"] == {"state": "on"}
        assert envelope["user_id"] == "sadeesha"
        assert "command_id" in envelope
        assert "timestamp" in envelope
        assert envelope["source"] == "rn_voice_agent"
        assert envelope["target_hub"] == "RN_HUB_MAIN"


def test_rabbitmq_env_and_settings_configuration():
    """Verify that settings loads the remote broker and routing configuration from .env."""
    from app.config import Settings
    custom_settings = Settings(
        rabbitmq_host="broker.example.com",
        rabbitmq_amqp_port=5672,
        rabbitmq_user="test_user",
        rabbitmq_password="test_password",
        rabbitmq_vhost="/vhost",
        rabbitmq_use_ssl=True,
        rabbitmq_command_exchange="custom_exchange",
        rabbitmq_command_queue="custom_queue",
        rabbitmq_command_routing_key="custom.key",
        api_host="0.0.0.0",
        api_port=8000
    )
    assert custom_settings.rabbitmq_host == "broker.example.com"
    assert custom_settings.rabbitmq_amqp_port == 5672
    assert custom_settings.rabbitmq_command_exchange == "custom_exchange"
    assert custom_settings.rabbitmq_command_queue == "custom_queue"
    assert custom_settings.rabbitmq_command_routing_key == "custom.key"
    assert custom_settings.api_host == "0.0.0.0"
    assert custom_settings.api_port == 8000
    # Verified SSL amqps URL generation
    assert custom_settings.rabbitmq_url == "amqps://test_user:test_password@broker.example.com:5672/vhost"

