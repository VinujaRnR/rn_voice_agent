"""Tests for schedules, reminders, and Sarah's general reasoning capabilities."""
import pytest
import time
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.conversation.manager import ConversationManager
from app.tools.reminders import set_reminder, list_reminders, cancel_reminder, check_due_reminders
from app.conversation.storage import ConversationStorage


@pytest.fixture
def storage():
    return ConversationStorage()


@pytest.fixture
def manager(storage):
    return ConversationManager(storage=storage)


def test_reminder_crud_storage(storage):
    session_id = f"test_crud_session_{uuid.uuid4().hex[:6]}"
    rem_id = f"rem_test_{uuid.uuid4().hex[:6]}"
    storage.create_reminder(
        reminder_id=rem_id,
        session_id=session_id,
        text="Drink water",
        due_at_timestamp=time.time() + 300,
        due_at_iso="2026-10-29T17:00:00",
        delay_seconds=300
    )

    active = storage.get_active_reminders(session_id)
    assert any(r["id"] == rem_id for r in active)

    cancelled = storage.cancel_reminder(rem_id, session_id)
    assert cancelled is True

    active_after = storage.get_active_reminders(session_id)
    assert not any(r["id"] == rem_id for r in active_after)


def test_reminder_tools_set_list_cancel():
    sess = f"test_tools_sess_{uuid.uuid4().hex[:6]}"
    set_res = set_reminder("check boiler", delay_seconds=10, session_id=sess)
    assert set_res["status"] == "success"
    assert "check boiler" in set_res["feedback"]

    list_res = list_reminders(session_id=sess)
    assert list_res["status"] == "success"
    assert list_res["count"] >= 1
    assert "check boiler" in list_res["feedback"]

    cancel_res = cancel_reminder("check boiler", session_id=sess)
    assert cancel_res["status"] == "success"


def test_reminder_trigger_worker(storage):
    sess = f"test_worker_sess_{uuid.uuid4().hex[:6]}"
    rem_id = f"rem_quick_{uuid.uuid4().hex[:6]}"
    storage.create_reminder(
        reminder_id=rem_id,
        session_id=sess,
        text="quick alert",
        due_at_timestamp=time.time() - 1,  # Already past due
        due_at_iso="2026-10-29T16:00:00",
        delay_seconds=0
    )

    due = check_due_reminders()
    assert any(d["id"] == rem_id for d in due)
    triggered_item = next(d for d in due if d["id"] == rem_id)
    assert "quick alert" in triggered_item["speech"]


@pytest.mark.asyncio
async def test_chat_endpoint_reminder_flow():
    transport = ASGITransport(app=app)
    sess = "test_chat_rem_sess"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Set a reminder
        res1 = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "Remind me to inspect the garden in 15 minutes"
        })
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["mode"] == "answer"
        assert "inspect the garden" in data1["speech"].lower()
        assert "15 minutes" in data1["speech"]

        # 2. Query active reminders
        res2 = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "What are my reminders?"
        })
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["mode"] == "answer"
        assert "inspect the garden" in data2["speech"].lower()

        # 3. Cancel reminder
        res3 = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "Cancel reminder"
        })
        assert res3.status_code == 200
        data3 = res3.json()
        assert data3["mode"] == "answer"
        assert "cancelled" in data3["speech"].lower()


@pytest.mark.asyncio
async def test_chat_endpoint_natural_language_reminder_reasoning():
    transport = ASGITransport(app=app)
    sess = "test_nl_reminder_reasoning"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "could you please remind me to take my pills in 4:30 p.m."
        })
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "answer"
        speech = data["speech"].lower()
        # Must reason cleanly and not quote conversational prefix as the task
        assert "could you please" not in speech
        assert "take" in speech and "pills" in speech
        assert "4:30" in speech


@pytest.mark.asyncio
async def test_chat_endpoint_general_reasoning_not_device_hijacked():
    transport = ASGITransport(app=app)
    sess = "test_reasoning_sess"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Questions containing words like "light" must NOT be hijacked into device status checks
        res = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "What is the speed of light?"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "answer"
        assert data["command"] is None
        # Speech should talk about speed / kilometers / miles / vacuum, not "the device is turned off"
        speech = data["speech"].lower()
        assert "turned off" not in speech
        assert "speed" in speech or "299" in speech or "kilometer" in speech or "mile" in speech


@pytest.mark.asyncio
async def test_reminders_rest_api():
    transport = ASGITransport(app=app)
    sess = "test_rest_rem_sess"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create via REST
        res_create = await ac.post("/api/reminders/", json={
            "text": "Call the veterinarian",
            "delay_minutes": 25,
            "session_id": sess
        })
        assert res_create.status_code == 200
        data = res_create.json()
        rem_id = data["reminder_id"]
        assert data["status"] == "success"

        # List via REST
        res_list = await ac.get(f"/api/reminders/?session_id={sess}")
        assert res_list.status_code == 200
        assert res_list.json()["count"] >= 1

        # Delete via REST
        res_del = await ac.delete(f"/api/reminders/{rem_id}?session_id={sess}")
        assert res_del.status_code == 200
        assert res_del.json()["status"] == "success"
