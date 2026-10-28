"""Unit tests for Step 8: Conversation memory, clarification, SQLite persistence, and Jarvis trigger word."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.conversation.storage import ConversationStorage
from app.conversation.manager import ConversationManager


@pytest.fixture
def temp_storage(tmp_path):
    db_file = str(tmp_path / "test_voice.db")
    storage = ConversationStorage(db_path=db_file)
    return storage


def test_sqlite_tables_created(temp_storage):
    """Verify that all 4 required tables are created in SQLite."""
    with temp_storage._get_connection() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}

    assert "sessions" in tables
    assert "messages" in tables
    assert "pending_actions" in tables
    assert "command_history" in tables


def test_sqlite_crud_operations(temp_storage):
    """Verify message logging, pending action tracking, and command history logging."""
    session_id = "test_crud_session"
    temp_storage.append_message(session_id, "user", "Turn on the lights.")
    temp_storage.append_message(session_id, "assistant", "Which lights should I turn on?")

    messages = temp_storage.get_session_messages(session_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Turn on the lights."

    # Pending action
    temp_storage.save_pending_action(
        session_id=session_id,
        action="set_power",
        parameters={"state": "on"},
        missing_fields=["device_id"]
    )
    pending = temp_storage.get_pending_action(session_id)
    assert pending is not None
    assert pending["action"] == "set_power"
    assert pending["missing_fields"] == ["device_id"]
    assert pending["status"] == "pending"

    # Resolve pending action
    temp_storage.resolve_pending_action(session_id)
    assert temp_storage.get_pending_action(session_id) is None

    # Record command
    temp_storage.record_command(
        command_id="cmd_001",
        session_id=session_id,
        action="set_power",
        target_device="98a316e6b658",
        state="sent",
        result={"status": "ok"}
    )
    history = temp_storage.get_command_history(session_id)
    assert len(history) == 1
    assert history[0]["command_id"] == "cmd_001"
    assert history[0]["target_device"] == "98a316e6b658"


@pytest.mark.asyncio
async def test_clarification_resolution_pass_condition():
    """Pass condition test:
    The assistant correctly resolves 'Turn on the lights' followed by 'Testing farm'
    into one complete intended command.
    """
    transport = ASGITransport(app=app)
    session_id = "clarification_pass_test"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Turn 1: "Turn on the lights."
        res1 = await ac.post("/api/chat", json={
            "session_id": session_id,
            "text": "Turn on the lights."
        })
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["mode"] == "clarify"
        assert "Which lights" in data1["speech"]
        assert "device_id" in data1["missing_fields"]
        assert data1["command"] is None

        # Turn 2: "Testing farm."
        res2 = await ac.post("/api/chat", json={
            "session_id": session_id,
            "text": "Testing farm."
        })
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["mode"] == "device_command"
        assert data2["command"] is not None
        assert data2["command"]["device_id"] == "98a316e6b658"
        assert data2["command"]["action"] == "set_power"
        assert data2["command"]["parameters"]["state"] == "on"
        assert "Sending the command to RN Hub" in data2["speech"]


@pytest.mark.asyncio
async def test_jarvis_wake_word_and_weather():
    """Verify Jarvis trigger word and general weather question handling."""
    transport = ASGITransport(app=app)
    session_id = "jarvis_weather_test"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Test 1: Just wake word
        res_wake = await ac.post("/api/chat", json={
            "session_id": session_id,
            "text": "Hey Jarvis"
        })
        assert res_wake.status_code == 200
        assert res_wake.json()["mode"] == "answer"
        assert "listening" in res_wake.json()["speech"].lower()

        # Test 2: Weather inquiry with trigger word
        res_weather = await ac.post("/api/chat", json={
            "session_id": session_id,
            "text": "Jarvis, what is the weather?"
        })
        assert res_weather.status_code == 200
        data_weather = res_weather.json()
        assert data_weather["mode"] == "answer"
        assert "weather" in data_weather["speech"].lower() or "24°C" in data_weather["speech"]


@pytest.mark.asyncio
async def test_jarvis_room_lights_command():
    """Verify general home/office room lights control with Jarvis trigger."""
    transport = ASGITransport(app=app)
    session_id = "jarvis_room_lights_test"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/chat", json={
            "session_id": session_id,
            "text": "Jarvis, turn on the room lights"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "device_command"
        assert data["command"]["device_id"] == "room_lights"
        assert data["command"]["action"] == "set_power"
        assert data["command"]["parameters"]["state"] == "on"


@pytest.mark.asyncio
async def test_alexa_wake_word_and_kitchen_lights():
    """Verify Alexa wake word and kitchen lights control."""
    transport = ASGITransport(app=app)
    session_id = "alexa_kitchen_test"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Alexa weather query
        res_weather = await ac.post("/api/chat", json={
            "session_id": session_id,
            "text": "Alexa, what's the weather today?"
        })
        assert res_weather.status_code == 200
        assert res_weather.json()["mode"] == "answer"
        assert "weather" in res_weather.json()["speech"].lower() or "24 degrees" in res_weather.json()["speech"].lower()

        # Alexa device command
        res_cmd = await ac.post("/api/chat", json={
            "session_id": session_id,
            "text": "Alexa, turn on the kitchen lights"
        })
        assert res_cmd.status_code == 200
        data_cmd = res_cmd.json()
        assert data_cmd["mode"] == "device_command"
        assert data_cmd["command"]["device_id"] == "kitchen_lights"
        assert data_cmd["command"]["action"] == "set_power"
        assert data_cmd["command"]["parameters"]["state"] == "on"



@pytest.mark.asyncio
async def test_unclear_device_asks_for_clarification():
    """If a request contains an unclear device, do not choose a device simply because it sounds similar.
    Ask for clarification.
    """
    transport = ASGITransport(app=app)
    session_id = "unclear_device_test"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Step 1: Initial ambiguous request
        await ac.post("/api/chat", json={
            "session_id": session_id,
            "text": "Turn on the lights."
        })

        # Step 2: Unclear device name that does not exist in registry
        res = await ac.post("/api/chat", json={
            "session_id": session_id,
            "text": "kitchen rooftop patio"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "clarify"
        assert data["command"] is None
        assert "device_id" in data["missing_fields"]


@pytest.mark.asyncio
async def test_sarah_all_pronunciations():
    """Verify that any phonetic pronunciation or spelling of Sarah triggers the assistant."""
    transport = ASGITransport(app=app)
    pronunciations = [
        "Sarah", "Sara", "Sera", "Serah", "Sahra", "Zarah", "Zara",
        "Saira", "Sierra", "Cera", "Ceira", "Syrah", "Surah",
        "Sarha", "Sarra", "Zahra", "Zera", "Sayrah",
        "Hey Sarah", "Hi Sara", "Ok Sera", "Hello Zarah"
    ]

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for pron in pronunciations:
            # 1. Wake word only invocation
            res = await ac.post("/api/chat", json={
                "session_id": f"sess_{pron.replace(' ', '_')}",
                "text": pron
            })
            assert res.status_code == 200
            data = res.json()
            assert data["mode"] == "answer"
            assert "sarah" in data["speech"].lower() or "listening" in data["speech"].lower()

        # 2. Command with pronunciation: "Sera, what is the weather?"
        res_cmd = await ac.post("/api/chat", json={
            "session_id": "sess_sera_weather",
            "text": "Sera, what is the weather?"
        })
        assert res_cmd.status_code == 200
        assert res_cmd.json()["mode"] == "answer"
        assert "weather" in res_cmd.json()["speech"].lower()

        # 3. Command with pronunciation: "Zara turn on room lights"
        res_lights = await ac.post("/api/chat", json={
            "session_id": "sess_zara_lights",
            "text": "Zara turn on room lights"
        })
        assert res_lights.status_code == 200
        assert res_lights.json()["mode"] == "device_command"
        assert res_lights.json()["command"]["device_id"] == "room_lights"


@pytest.mark.asyncio
async def test_sarah_wake_and_5_minute_silence_workflow():
    """Verify the full greeting -> follow-up commands -> 5 min silence auto-off -> re-trigger workflow."""
    import uuid
    transport = ASGITransport(app=app)
    session_id = f"sarah_silence_workflow_{uuid.uuid4().hex[:8]}"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Step 1: Initial state - check session status (starts not awake)
        status_res = await ac.get(f"/api/chat/session/{session_id}/status")
        assert status_res.status_code == 200
        assert status_res.json()["is_awake"] is False

        # Step 2: User greets Sarah
        wake_res = await ac.post("/api/chat", json={
            "session_id": session_id,
            "text": "Hey Sarah",
            "enforce_wake_standby": True
        })
        assert wake_res.status_code == 200
        data_wake = wake_res.json()
        assert data_wake["mode"] == "answer"
        assert "listening" in data_wake["speech"].lower() or "sarah" in data_wake["speech"].lower()

        # Check session is now awake with active seconds remaining
        status_after_wake = await ac.get(f"/api/chat/session/{session_id}/status")
        assert status_after_wake.json()["is_awake"] is True
        assert status_after_wake.json()["remaining_seconds"] > 290

        # Step 3: Tell a command WITHOUT repeating Sarah: "what is the weather?"
        cmd1 = await ac.post("/api/chat", json={
            "session_id": session_id,
            "text": "what is the weather?",
            "enforce_wake_standby": True
        })
        assert cmd1.status_code == 200
        assert "weather" in cmd1.json()["speech"].lower()

        # Step 4: Tell another command WITHOUT repeating Sarah: "turn on room lights"
        cmd2 = await ac.post("/api/chat", json={
            "session_id": session_id,
            "text": "turn on room lights",
            "enforce_wake_standby": True
        })
        assert cmd2.status_code == 200
        assert cmd2.json()["mode"] == "device_command"
        assert cmd2.json()["command"]["device_id"] == "room_lights"

        # Step 5: Simulate 5 minutes of silence passing (sleep session)
        await ac.post(f"/api/chat/session/{session_id}/sleep")
        status_sleep = await ac.get(f"/api/chat/session/{session_id}/status")
        assert status_sleep.json()["is_awake"] is False

        # If a command is given while in sleep mode with standby enforcement, Sarah prompts to greet her
        cmd_asleep = await ac.post("/api/chat", json={
            "session_id": session_id,
            "text": "turn off room lights",
            "enforce_wake_standby": True
        })
        assert cmd_asleep.status_code == 200
        assert "sleep mode" in cmd_asleep.json()["speech"].lower() or "sarah" in cmd_asleep.json()["speech"].lower()

        # Step 6: Greet Sarah again to trigger / wake back up!
        re_wake = await ac.post("/api/chat", json={
            "session_id": session_id,
            "text": "Sarah",
            "enforce_wake_standby": True
        })
        assert re_wake.status_code == 200
        assert "listening" in re_wake.json()["speech"].lower()

        # Verify she is awake again
        status_rewoken = await ac.get(f"/api/chat/session/{session_id}/status")
        assert status_rewoken.json()["is_awake"] is True


