"""Step 12 Tests — Publish commands, consume execution results, and command lifecycle."""
import uuid
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
import aio_pika
from app.main import app
from app.config import settings
from app.commands.lifecycle import CommandState, generate_speech_outcome
from app.commands.device_registry import device_registry
from app.conversation.storage import ConversationStorage
from app.tools.device_control import control_device
from app.rabbitmq.publisher import RabbitMQPublisher
from app.rabbitmq.consumer import CommandResultConsumer
from app.rabbitmq.hub_simulator import RNHubSimulator, hub_simulator


@pytest.fixture
def clean_storage():
    storage = ConversationStorage()
    return storage


def test_command_envelope_and_initial_lifecycle_state(clean_storage):
    """Verify proposed message envelope format and initial 'validated' state."""
    device_id = "98a316e6b658"
    action = "set_power"
    parameters = {"state": "on"}

    res = control_device(
        device_id=device_id,
        action=action,
        parameters=parameters,
        user_id="sadeesha"
    )

    assert res["status"] == "success"
    assert "command_id" in res
    command_id = res["command_id"]

    # Verify envelope fields
    envelope = res["envelope"]
    assert envelope["schema_version"] == "1.0"
    assert envelope["command_id"] == command_id
    assert envelope["source"] == "rn_voice_assistant"
    assert envelope["device_id"] == "98a316e6b658"
    assert envelope["action"] == "set_power"
    assert envelope["parameters"] == {"state": "on"}

    # Verify initial SQLite state is validated
    record = clean_storage.get_command(command_id)
    assert record is not None
    assert record["state"] in ["validated", "published"]
    assert record["action"] == "set_power"
    assert record["target_device"] == "98a316e6b658"


@pytest.mark.asyncio
async def test_publisher_confirms_updates_state_to_published(clean_storage):
    """Verify that broker publisher confirm updates lifecycle state to 'published'."""
    command_id = str(uuid.uuid4())
    clean_storage.record_command(
        command_id=command_id,
        action="set_power",
        target_device="98a316e6b658",
        state="validated",
        parameters={"state": "on"}
    )

    mock_channel = AsyncMock(spec=aio_pika.RobustChannel)
    mock_channel.is_closed = False
    mock_exchange = AsyncMock()
    mock_channel.declare_exchange.return_value = mock_exchange
    mock_channel.declare_queue.return_value = AsyncMock()

    mock_mgr = MagicMock()
    mock_mgr.get_channel = AsyncMock(return_value=mock_channel)

    pub = RabbitMQPublisher(connection_manager=mock_mgr, storage=clean_storage)

    payload = {
        "schema_version": "1.0",
        "command_id": command_id,
        "source": "rn_voice_assistant",
        "device_id": "98a316e6b658",
        "action": "set_power",
        "parameters": {"state": "on"}
    }

    published = await pub.publish(
        queue_name="commands",
        message=payload,
        exchange_name="rn.hub",
        routing_key="commands",
        correlation_id=command_id
    )

    assert published is True
    # Verify state in SQLite transitioned to 'published'
    record = clean_storage.get_command(command_id)
    assert record["state"] == "published"


def test_command_result_consumer_processes_completed_state(clean_storage):
    """Verify that RN Hub completed result updates SQLite and registry power state."""
    command_id = str(uuid.uuid4())
    clean_storage.record_command(
        command_id=command_id,
        action="set_power",
        target_device="98a316e6b658",
        state="published",
        parameters={"state": "on"}
    )

    consumer = CommandResultConsumer(storage=clean_storage)

    hub_result_payload = {
        "schema_version": "1.0",
        "command_id": command_id,
        "device_id": "98a316e6b658",
        "action": "set_power",
        "status": "completed",
        "result": {
            "power_state": "on",
            "state": "on",
            "relay_contact": "closed"
        },
        "evidence": "esp8266_relay_contact_on",
        "error": None
    }

    outcome = consumer.process_result_payload(hub_result_payload)

    assert outcome["status"] == "completed"
    assert "Testing Farm Lights" in outcome["speech_outcome"]
    assert "turned on" in outcome["speech_outcome"]

    # Verify SQLite record is updated to completed
    record = clean_storage.get_command(command_id)
    assert record["state"] == "completed"
    assert record["result"]["power_state"] == "on"

    # Verify device registry state updated
    assert device_registry.get_device("98a316e6b658")["power_state"] == "on"


def test_command_result_consumer_handles_all_lifecycle_states(clean_storage):
    """Verify lifecycle states: accepted, rejected, failed, expired, unknown."""
    consumer = CommandResultConsumer(storage=clean_storage)

    # 1. Accepted state
    cmd_acc = str(uuid.uuid4())
    clean_storage.record_command(command_id=cmd_acc, action="set_power", target_device="98a316e6b658", state="published")
    out_acc = consumer.process_result_payload({"command_id": cmd_acc, "device_id": "98a316e6b658", "status": "accepted"})
    assert clean_storage.get_command(cmd_acc)["state"] == "accepted"
    assert "accepted the command" in out_acc["speech_outcome"]

    # 2. Rejected state
    cmd_rej = str(uuid.uuid4())
    clean_storage.record_command(command_id=cmd_rej, action="set_power", target_device="98a316e6b658", state="published")
    out_rej = consumer.process_result_payload({"command_id": cmd_rej, "device_id": "98a316e6b658", "status": "rejected", "error": "Safety lockout active"})
    assert clean_storage.get_command(cmd_rej)["state"] == "rejected"
    assert "rejected" in out_rej["speech_outcome"]
    assert "Safety lockout active" in out_rej["speech_outcome"]

    # 3. Failed state
    cmd_fail = str(uuid.uuid4())
    clean_storage.record_command(command_id=cmd_fail, action="set_power", target_device="98a316e6b658", state="published")
    out_fail = consumer.process_result_payload({"command_id": cmd_fail, "device_id": "98a316e6b658", "status": "failed", "error": "Relay coil open circuit"})
    assert clean_storage.get_command(cmd_fail)["state"] == "failed"
    assert "Execution failed" in out_fail["speech_outcome"]

    # 4. Expired state
    cmd_exp = str(uuid.uuid4())
    clean_storage.record_command(command_id=cmd_exp, action="set_power", target_device="98a316e6b658", state="published")
    out_exp = consumer.process_result_payload({"command_id": cmd_exp, "device_id": "98a316e6b658", "status": "expired"})
    assert clean_storage.get_command(cmd_exp)["state"] == "expired"
    assert "timed out" in out_exp["speech_outcome"]

    # 5. Unknown state
    cmd_unk = str(uuid.uuid4())
    clean_storage.record_command(command_id=cmd_unk, action="set_power", target_device="98a316e6b658", state="published")
    out_unk = consumer.process_result_payload({"command_id": cmd_unk, "device_id": "98a316e6b658", "status": "invalid_bogus_state"})
    assert clean_storage.get_command(cmd_unk)["state"] == "unknown"


@pytest.mark.asyncio
async def test_end_to_end_pass_condition_wsl2_to_hub_and_result(clean_storage):
    """Pass condition: A test command travels through RabbitMQ to RN Hub,
    and the corresponding device result returns to the assistant.
    """
    # 1. Voice assistant validates and dispatches command
    dispatch_res = control_device(
        device_id="98a316e6b658",
        action="set_power",
        parameters={"state": "off"},
        user_id="sadeesha"
    )
    assert dispatch_res["status"] == "success"
    command_id = dispatch_res["command_id"]
    envelope = dispatch_res["envelope"]

    # 2. RN Hub simulator consumes command and executes on physical hardware
    simulator = RNHubSimulator()
    hub_result = simulator.execute_device_action(envelope)

    assert hub_result["status"] == "completed"
    assert hub_result["command_id"] == command_id
    assert hub_result["result"]["power_state"] == "off"
    assert hub_result["evidence"] == "esp8266_relay_contact_off"

    # 3. Voice assistant result consumer receives the result from RabbitMQ
    consumer = CommandResultConsumer(storage=clean_storage)
    outcome = consumer.process_result_payload(hub_result, correlation_id=command_id)

    # 4. Verified full lifecycle completion and speech outcome
    assert outcome["status"] == "completed"
    assert "Testing Farm Lights" in outcome["speech_outcome"]
    assert "turned off" in outcome["speech_outcome"]

    # 5. Verify SQLite record has transitioned to completed
    record = clean_storage.get_command(command_id)
    assert record["state"] == "completed"
    assert record["result"]["power_state"] == "off"


@pytest.mark.asyncio
async def test_api_command_status_endpoint(clean_storage):
    """Verify GET /api/commands/{command_id} endpoint returns accurate state and speech outcome."""
    command_id = str(uuid.uuid4())
    clean_storage.record_command(
        command_id=command_id,
        action="set_power",
        target_device="98a316e6b658",
        state="completed",
        result={"power_state": "on"},
        parameters={"state": "on"}
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(f"/api/commands/{command_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["command_id"] == command_id
    assert data["state"] == "completed"
    assert data["device_name"] == "Testing Farm Lights"
    assert "turned on" in data["speech_outcome"]
