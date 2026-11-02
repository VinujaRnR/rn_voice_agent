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


def test_parse_reminder_expression_oclock_and_natural_time():
    from datetime import datetime
    from app.tools.reminders import parse_reminder_expression

    # 1. "could you please remind me to take my pills in 3 o'clock" at 14:50
    t1 = datetime(2026, 11, 2, 14, 50, 0)
    p1 = parse_reminder_expression("could you please remind me to take my pills in 3 o'clock", now=t1)
    assert p1["text"] == "take your pills"
    assert p1["delay_seconds"] == 600  # 10 minutes until 15:00
    assert "3:00 PM" in p1["delay_label"]
    assert p1["is_clock_time"] is True

    # 2. "remind me at three o'clock to take my pills"
    p2 = parse_reminder_expression("remind me at three o'clock to take my pills", now=t1)
    assert p2["text"] == "take your pills"
    assert p2["delay_seconds"] == 600
    assert "3:00 PM" in p2["delay_label"]
    assert p2["is_clock_time"] is True

    # 3. "remind me to call mom at 3"
    p3 = parse_reminder_expression("remind me to call mom at 3", now=t1)
    assert p3["text"] == "call mom"
    assert p3["delay_seconds"] == 600
    assert "3:00 PM" in p3["delay_label"]


def test_reminder_alert_pronoun_second_person(storage):
    sess = f"test_pronoun_sess_{uuid.uuid4().hex[:6]}"
    rem_id = f"rem_pills_{uuid.uuid4().hex[:6]}"
    # Even if stored as "take my pills"
    storage.create_reminder(
        reminder_id=rem_id,
        session_id=sess,
        text="take my pills",
        due_at_timestamp=time.time() - 1,
        due_at_iso="2026-11-02T15:00:00",
        delay_seconds=0
    )

    due = check_due_reminders()
    item = next(d for d in due if d["id"] == rem_id)
    assert "take your pills" in item["speech"]
    assert "take my pills" not in item["speech"]
    assert item["speech"] == "Reminder alert: It's time to take your pills."


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
async def test_chat_endpoint_oclock_reminder_reasoning():
    transport = ASGITransport(app=app)
    sess = "test_oclock_reminder_reasoning"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "could you please remind me to take my pills in 3 o'clock"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "answer"
        speech = data["speech"].lower()
        # Must reason cleanly: task is pills, time is 3:00 (not 3:09), and asks recurrence
        assert "take" in speech and "pills" in speech
        assert "3:00" in speech or "3 o'clock" in speech or "3:00 pm" in speech or "3 pm" in speech
        assert "3:09" not in speech
        assert any(w in speech for w in ["daily", "weekly", "monthly", "custom", "only for that day"])


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


@pytest.mark.asyncio
async def test_reminder_recurrence_prompt_and_clarification():
    """Verify that when a user sets a reminder without recurrence, Sarah asks
    whether it is daily, weekly, monthly, custom, or only for that day,
    and updates the recurrence on the next turn."""
    transport = ASGITransport(app=app)
    sess = f"test_recurrence_prompt_sess_{uuid.uuid4().hex[:6]}"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Turn 1: User sets reminder without recurrence
        res1 = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "could you please remind me to take my pills at 4:30 p.m."
        })
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["mode"] == "answer"
        speech1 = data1["speech"].lower()
        assert "take" in speech1 and "pills" in speech1
        # Sarah must ask about recurrence
        assert any(w in speech1 for w in ["daily", "weekly", "monthly", "custom", "only for that day"])

        # Turn 2: User responds "daily"
        res2 = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "daily"
        })
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["mode"] == "answer"
        assert "daily" in data2["speech"].lower()

        # Verify in database that reminder has recurrence 'daily'
        res_list = await ac.get(f"/api/reminders/?session_id={sess}")
        assert res_list.status_code == 200
        reminders = res_list.json()["reminders"]
        assert len(reminders) == 1
        assert reminders[0]["recurrence"] == "daily"


@pytest.mark.asyncio
async def test_reminder_upfront_recurrence():
    """Verify that when recurrence is specified upfront, Sarah sets it directly without asking."""
    transport = ASGITransport(app=app)
    sess = f"test_upfront_recurrence_sess_{uuid.uuid4().hex[:6]}"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Upfront daily
        res1 = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "Remind me daily to take my vitamins at 8:00 am"
        })
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["mode"] == "answer"
        assert "daily" in data1["speech"].lower()
        # Should not ask the recurrence question again
        assert "would you like this reminder for" not in data1["speech"].lower()

        # 2. Upfront weekly
        res2 = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "Set a weekly reminder to inspect the garden in 20 minutes"
        })
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["mode"] == "answer"
        assert "weekly" in data2["speech"].lower()
        assert "would you like this reminder for" not in data2["speech"].lower()


@pytest.mark.asyncio
async def test_reminder_rest_api_recurrence():
    """Verify recurrence parameter in REST API and PATCH recurrence endpoint."""
    transport = ASGITransport(app=app)
    sess = "test_rest_api_recurrence_sess"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create with recurrence
        res_create = await ac.post("/api/reminders/", json={
            "text": "Pay electric bill",
            "delay_minutes": 60,
            "recurrence": "monthly",
            "session_id": sess
        })
        assert res_create.status_code == 200
        data = res_create.json()
        rem_id = data["reminder_id"]
        assert data["recurrence"] == "monthly"

        # Update recurrence via PATCH
        res_patch = await ac.patch(f"/api/reminders/{rem_id}/recurrence", json={
            "recurrence": "weekly",
            "session_id": sess
        })
        assert res_patch.status_code == 200
        assert res_patch.json()["recurrence"] == "weekly"

        # Verify listed item reflects updated recurrence
        res_list = await ac.get(f"/api/reminders/?session_id={sess}")
        assert res_list.status_code == 200
        rems = [r for r in res_list.json()["reminders"] if r["id"] == rem_id]
        assert len(rems) == 1
        assert rems[0]["recurrence"] == "weekly"


@pytest.mark.asyncio
async def test_incomplete_reminder_clarification_and_continuation():
    """Verify Sarah asks context for incomplete reminder queries like 'can you remind me to take' and continues seamlessly."""
    transport = ASGITransport(app=app)
    sess = f"test_incomplete_flow_{uuid.uuid4().hex[:6]}"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Turn 1: Incomplete query lacking task object and time
        res1 = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "can you remind me to take"
        })
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["mode"] == "clarify"
        assert "task" in data1["missing_fields"]
        assert "target_time" in data1["missing_fields"]
        assert "what would you like me to remind you to take" in data1["speech"].lower()

        # Verify no bogus reminder for 'take' was scheduled
        list_res = await ac.get(f"/api/reminders/?session_id={sess}")
        assert list_res.status_code == 200
        assert not any(r["text"] == "take" for r in list_res.json()["reminders"])

        # Turn 2: User provides context and clock time
        res2 = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "my pills in 3 o'clock"
        })
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["mode"] == "answer"
        assert "take your pills" in data2["speech"].lower()
        assert "3:00 pm" in data2["speech"].lower()
        assert "daily, weekly, monthly, custom, or only for that day" in data2["speech"].lower()

        # Verify reminder is properly registered in storage with second-person pronoun
        list_res2 = await ac.get(f"/api/reminders/?session_id={sess}")
        assert list_res2.status_code == 200
        pills_rems = [r for r in list_res2.json()["reminders"] if "take your pills" in r["text"]]
        assert len(pills_rems) == 1
        assert pills_rems[0]["recurrence"] in ["once", None]

        # Turn 3: User answers recurrence
        res3 = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "daily"
        })
        assert res3.status_code == 200
        data3 = res3.json()
        assert data3["mode"] == "answer"
        assert "daily" in data3["speech"].lower()

        # Verify recurrence updated in storage
        list_res3 = await ac.get(f"/api/reminders/?session_id={sess}")
        assert list_res3.status_code == 200
        pills_rems3 = [r for r in list_res3.json()["reminders"] if "take your pills" in r["text"]]
        assert len(pills_rems3) == 1
        assert pills_rems3[0]["recurrence"] == "daily"


@pytest.mark.asyncio
async def test_incomplete_reminder_other_verbs():
    """Verify incomplete verbs like call, buy, or bare reminder ask for context."""
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # "remind me to call"
        r1 = await ac.post("/api/chat", json={
            "session_id": f"sess_call_{uuid.uuid4().hex[:6]}",
            "text": "remind me to call"
        })
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["mode"] == "clarify"
        assert "who would you like me to remind you to call" in d1["speech"].lower()

        # "can you remind me to buy"
        r2 = await ac.post("/api/chat", json={
            "session_id": f"sess_buy_{uuid.uuid4().hex[:6]}",
            "text": "can you remind me to buy"
        })
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["mode"] == "clarify"
        assert "what would you like me to remind you to buy" in d2["speech"].lower()

        # "can you remind me"
        r3 = await ac.post("/api/chat", json={
            "session_id": f"sess_bare_{uuid.uuid4().hex[:6]}",
            "text": "can you remind me"
        })
        assert r3.status_code == 200
        d3 = r3.json()
        assert d3["mode"] == "clarify"
        assert "what would you like me to remind you about" in d3["speech"].lower()


@pytest.mark.asyncio
async def test_reminder_over_cleared_when_only_for_that_day(storage):
    """When a reminder is past due and set for that day only ('once'), it must clear from active reminders."""
    sess = f"test_over_rem_{uuid.uuid4().hex[:6]}"
    rem_id = f"rem_{uuid.uuid4().hex[:8]}"
    storage.create_reminder(
        reminder_id=rem_id,
        session_id=sess,
        text="take your pills",
        due_at_timestamp=time.time() - 60,  # 1 minute in the past
        due_at_iso="2026-11-02T16:19:00",
        delay_seconds=0,
        recurrence="once"
    )

    # Active reminders should auto-clear past due one-day reminders
    active = storage.get_active_reminders(sess)
    assert len(active) == 0

    from app.tools.reminders import list_reminders
    res = list_reminders(session_id=sess)
    assert res["count"] == 0
    assert "no active reminders" in res["feedback"].lower()


@pytest.mark.asyncio
async def test_chat_reminder_reasoning_and_followups():
    """Verify Gemini reasoning handles 'how many reminders', 'at what time' follow-up, and past reminder explanations."""
    transport = ASGITransport(app=app)
    sess = f"test_reasoning_flow_{uuid.uuid4().hex[:6]}"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Ask "how many reminders right now" when empty
        r1 = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "how many reminders right now"
        })
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["mode"] == "answer"
        assert any(w in d1["speech"].lower() for w in ["no active reminders", "don't have any", "do not have any", "0"])

        # 2. Cancel/clear when empty should be graceful
        r2 = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "no I just need to clear it"
        })
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["mode"] == "answer"
        assert any(w in d2["speech"].lower() for w in ["no active reminders", "don't have any", "cancelled", "cleared"])



