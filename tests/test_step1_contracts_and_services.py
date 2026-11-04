"""Tests for Step 1: Service layer, domain contracts, and legacy compatibility adapters."""
import pytest
from app.schemas.contracts import (
    ChatRequestContract,
    ChatResponseContract,
    DeviceControlRequestContract,
    DeviceControlResponseContract,
    ReminderCreateRequestContract,
    ReminderResponseContract
)
from app.services.session_service import session_service, LegacySessionAdapter
from app.services.chat_service import chat_service
from app.services.device_service import device_service
from app.services.reminder_service import reminder_service


def test_legacy_session_adapter_fallback():
    """Verify legacy adapter provides safe fallbacks when identity is omitted."""
    # When omitted
    ctx = session_service.resolve_context()
    assert ctx.is_legacy is True
    assert ctx.session_id == LegacySessionAdapter.DEFAULT_FALLBACK_SESSION
    assert ctx.user_id == LegacySessionAdapter.DEFAULT_FALLBACK_USER

    # When explicitly provided
    custom_ctx = session_service.resolve_context(
        session_id="session_margaret_123",
        user_id="user_margaret_456",
        household_id="house_sydney_789"
    )
    assert custom_ctx.is_legacy is False
    assert custom_ctx.session_id == "session_margaret_123"
    assert custom_ctx.user_id == "user_margaret_456"
    assert custom_ctx.household_id == "house_sydney_789"


def test_contracts_validation():
    """Verify request and response contract data integrity."""
    chat_req = ChatRequestContract(message="Hello Sarah")
    assert chat_req.get_query() == "Hello Sarah"

    chat_resp = ChatResponseContract(
        mode="answer",
        speech="Hello! How can I assist you?",
        missing_fields=[]
    )
    assert chat_resp.mode == "answer"
    assert chat_resp.speech == "Hello! How can I assist you?"

    dev_req = DeviceControlRequestContract(
        device_id="light_glow_1",
        action="LIGHT_ON",
        parameters={"state": "on"}
    )
    assert dev_req.device_id == "light_glow_1"

    rem_req = ReminderCreateRequestContract(
        text="Take medicine",
        delay_minutes=10,
        recurrence="daily"
    )
    assert rem_req.text == "Take medicine"
    assert rem_req.recurrence == "daily"


@pytest.mark.asyncio
async def test_chat_service_wake_and_sleep():
    """Verify chat service handles wake word and sleep modes."""
    # Wake word only
    wake_resp = await chat_service.process_chat_turn(
        ChatRequestContract(message="Sarah", session_id="test_service_session")
    )
    assert wake_resp.mode == "answer"
    assert "Sarah" in wake_resp.speech or "Hello" in wake_resp.speech

    # Sleep intent
    sleep_resp = await chat_service.process_chat_turn(
        ChatRequestContract(message="go to sleep", session_id="test_service_session")
    )
    assert sleep_resp.mode == "answer"
    assert "night" in sleep_resp.speech.lower() or "sleep" in sleep_resp.speech.lower()


@pytest.mark.asyncio
async def test_chat_service_device_command():
    """Verify chat service dispatches verified device commands through service layer."""
    cmd_resp = await chat_service.process_chat_turn(
        ChatRequestContract(message="turn on testing farm lights", session_id="test_service_cmd_session")
    )
    assert cmd_resp.mode == "device_command"
    assert cmd_resp.command is not None
    assert cmd_resp.command.device_id in ["98a316e6b658", "testing farm lights"]


@pytest.mark.asyncio
async def test_chat_service_reminder():
    """Verify chat service schedules reminders through service layer."""
    rem_resp = await chat_service.process_chat_turn(
        ChatRequestContract(message="remind me to check the oven in 20 minutes", session_id="test_service_rem_session")
    )
    assert "oven" in rem_resp.speech.lower() or (rem_resp.reminder and "oven" in rem_resp.reminder.task.lower())


def test_device_service_resolution():
    """Verify device service identifier resolution."""
    resolved = device_service.resolve_device("glow light")
    assert resolved == "3417ebc3b479"


def test_reminder_service_lifecycle():
    """Verify reminder service creation, listing, and cancellation."""
    req = ReminderCreateRequestContract(
        text="Take heart medicine",
        delay_minutes=15,
        session_id="test_rem_svc_session",
        recurrence="once"
    )
    res = reminder_service.create_reminder(req)
    assert res.reminder_id.startswith("rem_")

    active = reminder_service.list_active(session_id="test_rem_svc_session")
    assert any(r["reminder_id"] == res.reminder_id for r in active)

    cancelled = reminder_service.cancel(res.reminder_id, session_id="test_rem_svc_session")
    assert cancelled is True

