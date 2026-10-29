"""Unit tests for Step 7: Gemini structured JSON responses and cross-field validation."""
import pytest
from pydantic import ValidationError
from app.gemini.schemas import GeminiResponse, DeviceCommand


def test_valid_normal_answer_response():
    """Example normal response from Step 7 specification."""
    data = {
        "mode": "answer",
        "speech": "Hello, how can I help you?",
        "command": None,
        "missing_fields": []
    }
    response = GeminiResponse.model_validate(data)
    assert response.mode == "answer"
    assert response.speech == "Hello, how can I help you?"
    assert response.command is None
    assert response.missing_fields == []
    assert response.is_executable() is False


def test_valid_clarification_response():
    """Example clarification response from Step 7 specification."""
    data = {
        "mode": "clarify",
        "speech": "Which lights should I turn on?",
        "command": None,
        "missing_fields": ["device_id"]
    }
    response = GeminiResponse.model_validate(data)
    assert response.mode == "clarify"
    assert response.speech == "Which lights should I turn on?"
    assert response.command is None
    assert response.missing_fields == ["device_id"]
    assert response.is_executable() is False


def test_valid_device_command_response():
    """Example command proposal from Step 7 specification."""
    data = {
        "mode": "device_command",
        "speech": None,
        "command": {
            "device_id": "98a316e6b658",
            "action": "set_power",
            "parameters": {
                "state": "on"
            }
        },
        "missing_fields": []
    }
    response = GeminiResponse.model_validate(data)
    assert response.mode == "device_command"
    assert response.command is not None
    assert response.command.device_id == "98a316e6b658"
    assert response.command.action == "set_power"
    assert response.command.parameters == {"state": "on"}
    assert response.is_executable() is True


def test_device_command_without_command_object_fails():
    """Cross-field validation: a device_command must have a command object."""
    with pytest.raises(ValidationError) as exc_info:
        GeminiResponse.model_validate({
            "mode": "device_command",
            "speech": None,
            "command": None,
            "missing_fields": []
        })
    assert "A device_command response must have a valid command object" in str(exc_info.value)


def test_clarify_without_speech_fails():
    """Cross-field validation: a clarify response must have a question in speech."""
    with pytest.raises(ValidationError) as exc_info:
        GeminiResponse.model_validate({
            "mode": "clarify",
            "speech": None,
            "command": None,
            "missing_fields": ["device_id"]
        })
    assert "A clarify response must include a question in speech" in str(exc_info.value)


def test_clarify_with_empty_speech_fails():
    """Cross-field validation: a clarify response must not have blank speech."""
    with pytest.raises(ValidationError) as exc_info:
        GeminiResponse.model_validate({
            "mode": "clarify",
            "speech": "   ",
            "command": None,
            "missing_fields": ["device_id"]
        })
    assert "A clarify response must include a question in speech" in str(exc_info.value)


def test_invalid_responses_never_reach_executor():
    """Ensure is_executable guard blocks non-commands or partial commands."""
    # Clarify response
    clarify = GeminiResponse(
        mode="clarify",
        speech="Which zone?",
        command=None,
        missing_fields=["zone"]
    )
    assert clarify.is_executable() is False

    # Answer response
    answer = GeminiResponse(
        mode="answer",
        speech="Today is sunny.",
        command=None,
        missing_fields=[]
    )
    assert answer.is_executable() is False


def test_valid_response_with_chain_of_thought_reasoning():
    """Verify that GeminiResponse properly accepts and exposes internal reasoning traces."""
    data = {
        "reasoning": "User asked what the weather is in Colombo. Intent is weather inquiry. No device control needed.",
        "mode": "answer",
        "speech": "The weather in Colombo is 28 degrees and sunny.",
        "command": None,
        "missing_fields": []
    }
    response = GeminiResponse.model_validate(data)
    assert response.reasoning is not None
    assert "Intent is weather inquiry" in response.reasoning
    assert response.mode == "answer"


def test_device_command_with_reasoning():
    """Verify device command with step-by-step reasoning."""
    data = {
        "reasoning": "User requested 'turn on testing farm lights'. Target device is '98a316e6b658'. Action is 'set_power' with state='on'.",
        "mode": "device_command",
        "speech": "Okay, turning on the testing farm lights.",
        "command": {
            "device_id": "98a316e6b658",
            "action": "set_power",
            "parameters": {
                "state": "on"
            }
        },
        "missing_fields": []
    }
    response = GeminiResponse.model_validate(data)
    assert response.reasoning is not None
    assert response.is_executable() is True
    assert response.command.device_id == "98a316e6b658"
