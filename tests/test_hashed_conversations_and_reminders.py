"""Unit and integration tests for hashed conversation storage, future references, and voice assistant reminders."""
import pytest
import time
import uuid
import hashlib
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.conversation.storage import (
    ConversationStorage,
    compute_content_hash,
    compute_user_hash,
    compute_turn_hash
)
from app.context.memory import conversation_memory
from app.context.builder import context_builder
from app.tools.reminders import set_reminder, list_reminders, cancel_reminder, check_due_reminders


@pytest.fixture
def storage():
    return ConversationStorage()


def test_sha256_hash_computation():
    """Verify deterministic SHA-256 cryptographic hashing for content, user, and conversational turns."""
    text = "Please remind me to water the plants"
    expected = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
    assert compute_content_hash(text) == expected
    assert len(compute_content_hash(text)) == 64

    user_hash = compute_user_hash("alice")
    assert user_hash == hashlib.sha256("alice".encode("utf-8")).hexdigest()
    assert len(user_hash) == 64

    turn_hash = compute_turn_hash("sess_1", "user", text, "2026-10-30T10:00:00")
    assert len(turn_hash) == 64


def test_messages_table_hashed_storage(storage):
    """Verify messages table stores turns with content_hash, turn_hash, and user_hash."""
    sess = f"test_hash_sess_{uuid.uuid4().hex[:6]}"
    record = storage.append_message(
        session_id=sess,
        role="user",
        content="I love robotic automation",
        user_id="user_test_01"
    )

    assert "content_hash" in record
    assert "turn_hash" in record
    assert "user_hash" in record
    assert record["content_hash"] == compute_content_hash("I love robotic automation")

    # Fetch stored messages for the session
    messages = storage.get_session_messages(sess)
    assert len(messages) >= 1
    last_msg = messages[-1]
    assert last_msg["content"] == "I love robotic automation"
    assert last_msg["content_hash"] == record["content_hash"]
    assert len(last_msg["content_hash"]) == 64


def test_cross_session_conversation_references(storage):
    """Verify conversation_references allows recalling past conversations across different sessions."""
    user_id = f"user_{uuid.uuid4().hex[:6]}"
    sess1 = f"sess_1_{uuid.uuid4().hex[:6]}"
    sess2 = f"sess_2_{uuid.uuid4().hex[:6]}"

    # Save turn in session 1
    storage.append_message(sess1, "user", "My favorite cuisine is Japanese sushi", user_id=user_id)
    storage.append_message(sess1, "assistant", "Noted, you love sushi!", user_id=user_id)

    # In session 2, query previous conversation references
    past_refs = storage.get_user_previous_conversations(user_id=user_id, exclude_session_id=sess2)
    assert len(past_refs) >= 2
    contents = [r["content"] for r in past_refs]
    assert "My favorite cuisine is Japanese sushi" in contents

    # Search past conversations by keyword
    search_results = storage.search_previous_conversations("sushi", user_id=user_id)
    assert len(search_results) >= 1
    assert "sushi" in search_results[0]["content"].lower()
    assert search_results[0]["content_hash"] is not None

    # Fetch by hash
    c_hash = compute_content_hash("My favorite cuisine is Japanese sushi")
    by_hash = storage.get_conversation_by_hash(c_hash)
    assert by_hash is not None
    assert by_hash["content"] == "My favorite cuisine is Japanese sushi"


def test_context_builder_includes_hashed_references():
    """Verify dynamic context builder injects past conversation references for future reference."""
    sess = f"ctx_sess_{uuid.uuid4().hex[:6]}"
    conversation_memory.record_turn(sess, "What is the capital of France?", "The capital is Paris.")

    ctx = context_builder.build_context(session_id=sess)
    assert "conversation" in ctx
    conv_ctx = ctx["conversation"]
    assert "recent_messages" in conv_ctx
    assert "past_references" in conv_ctx
    if conv_ctx["recent_messages"]:
        assert "content_hash" in conv_ctx["recent_messages"][-1]


@pytest.mark.asyncio
async def test_chat_endpoint_stores_hashes_and_future_references():
    """Verify /api/chat writes hashed turns and can retrieve references via REST API."""
    transport = ASGITransport(app=app)
    sess = f"test_rest_hash_{uuid.uuid4().hex[:6]}"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Turn 1
        res1 = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "What time is it in Tokyo?"
        })
        assert res1.status_code == 200

        # Check session history endpoint contains hashes
        res_hist = await ac.get(f"/api/chat/history?session_id={sess}")
        assert res_hist.status_code == 200
        hist_data = res_hist.json()
        assert hist_data["count"] >= 2
        user_msg = hist_data["messages"][0]
        assert "content_hash" in user_msg
        assert len(user_msg["content_hash"]) == 64

        # Search past conversations via REST
        res_search = await ac.get(f"/api/chat/search?q=Tokyo")
        assert res_search.status_code == 200
        search_data = res_search.json()
        assert search_data["count"] >= 1

        # Retrieve by hash via REST
        msg_hash = user_msg["content_hash"]
        res_hash = await ac.get(f"/api/chat/by-hash/{msg_hash}")
        assert res_hash.status_code == 200
        assert res_hash.json()["content"] == "What time is it in Tokyo?"


@pytest.mark.asyncio
async def test_voice_assistant_reminder_instructions():
    """Verify assistant acts as a reminder for user instructions to remind something."""
    transport = ASGITransport(app=app)
    sess = f"test_reminder_instructions_{uuid.uuid4().hex[:6]}"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. User gives instruction to remind something
        res_set = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "Sarah, remind me to check the oven in 10 minutes"
        })
        assert res_set.status_code == 200
        set_data = res_set.json()
        assert set_data["mode"] == "answer"
        assert "check the oven" in set_data["speech"].lower()

        # 2. Inquire about reminders
        res_list = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "What are my reminders?"
        })
        assert res_list.status_code == 200
        list_data = res_list.json()
        assert list_data["mode"] == "answer"
        assert "oven" in list_data["speech"].lower()

        # 3. Instruction to cancel reminder
        res_cancel = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "Cancel my reminder"
        })
        assert res_cancel.status_code == 200
        cancel_data = res_cancel.json()
        assert cancel_data["mode"] == "answer"
        assert "cancel" in cancel_data["speech"].lower()


@pytest.mark.asyncio
async def test_proactive_due_reminder_trigger():
    """Verify due reminders trigger proactive alerts for the voice assistant."""
    sess = f"proactive_rem_sess_{uuid.uuid4().hex[:6]}"
    # Set reminder that is immediately due
    res = set_reminder("take vitamin D supplement", delay_seconds=5, session_id=sess)
    assert res["status"] == "success"
    rid = res["reminder_id"]

    # Sleep until due time (5 seconds)
    import asyncio
    await asyncio.sleep(5.1)

    # Query due endpoint
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res_due = await ac.get("/api/reminders/due")
        assert res_due.status_code == 200
        data = res_due.json()
        assert "due_count" in data
        assert "triggered" in data
        assert "recent_history" in data
        matched = [r for r in data["triggered"] if r["id"] == rid]
        assert len(matched) == 1
        assert "vitamin D supplement" in matched[0]["text"]

        # Acknowledge the reminder
        res_ack = await ac.post("/api/reminders/ack", json={"reminder_ids": [rid]})
        assert res_ack.status_code == 200
        assert res_ack.json()["status"] == "success"

        # Subsequent poll must NOT return acknowledged reminder
        res_due2 = await ac.get("/api/reminders/due")
        assert res_due2.status_code == 200
        data2 = res_due2.json()
        matched2 = [r for r in data2["triggered"] if r["id"] == rid]
        assert len(matched2) == 0


def test_reminder_with_dot_clock_time_and_turn_of_typo():
    """Verify 'remind me to turn of the lights in 11.50 am' parses target time and clean task."""
    from datetime import datetime
    from app.tools.reminders import parse_reminder_expression
    simulated_now = datetime(2026, 10, 30, 11, 48, 0)
    parsed = parse_reminder_expression("remind me to turn of the lights in 11.50 am", now=simulated_now)
    assert parsed["text"] == "turn off the lights"
    assert parsed["delay_seconds"] == 120
    assert "11:50 AM" in parsed["delay_label"]
    assert parsed["is_clock_time"] is True


@pytest.mark.asyncio
async def test_cancel_all_reminders_and_cancel_x_reminder():
    """Verify that 'cancel reminder' cancels all active reminders,
    and 'cancel x reminder' cancels only the matching reminder."""
    transport = ASGITransport(app=app)
    sess = f"test_cancel_x_sess_{uuid.uuid4().hex[:6]}"

    # 1. Schedule 3 separate reminders
    set_reminder("check the oven", delay_seconds=600, session_id=sess)
    set_reminder("drink the porridge", delay_seconds=600, session_id=sess)
    set_reminder("turn off the lights", delay_seconds=600, session_id=sess)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Check that 3 reminders are currently active
        res_list1 = await ac.get(f"/api/reminders/?session_id={sess}")
        assert res_list1.status_code == 200
        assert res_list1.json()["count"] == 3

        # 2. Cancel specific "oven" reminder: "Sarah, cancel oven reminder"
        res_cancel_oven = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "Sarah, cancel oven reminder"
        })
        assert res_cancel_oven.status_code == 200
        cancel_oven_data = res_cancel_oven.json()
        assert cancel_oven_data["mode"] == "answer"
        assert "oven" in cancel_oven_data["speech"].lower()
        assert "cancel" in cancel_oven_data["speech"].lower()

        # Check active reminders: "check the oven" is gone, 2 remain
        res_list2 = await ac.get(f"/api/reminders/?session_id={sess}")
        assert res_list2.status_code == 200
        rem_texts = [r["text"] for r in res_list2.json()["reminders"]]
        assert "check the oven" not in rem_texts
        assert "drink the porridge" in rem_texts
        assert "turn off the lights" in rem_texts
        assert res_list2.json()["count"] == 2

        # 3. Cancel all remaining reminders: "Sarah, cancel reminder"
        res_cancel_all = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "Sarah, cancel reminder"
        })
        assert res_cancel_all.status_code == 200
        cancel_all_data = res_cancel_all.json()
        assert cancel_all_data["mode"] == "answer"
        assert "cancel" in cancel_all_data["speech"].lower()
        assert any(w in cancel_all_data["speech"].lower() for w in ["all", "2", "two", "reminders"])

        # Check active reminders: 0 remain
        res_list3 = await ac.get(f"/api/reminders/?session_id={sess}")
        assert res_list3.status_code == 200
        assert res_list3.json()["count"] == 0

        # 4. Cancel again when none exist
        res_cancel_none = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "Cancel reminders"
        })
        assert res_cancel_none.status_code == 200
        speech_none = res_cancel_none.json()["speech"].lower()
        assert "active reminders" in speech_none or "no reminders" in speech_none or "cancel" in speech_none


@pytest.mark.asyncio
async def test_cancel_reminder_by_scheduled_clock_time():
    """Verify that 'cancel 4 pm reminder now' successfully matches and cancels
    a reminder scheduled for 4 PM or proximate time (e.g., 3:59 PM)."""
    transport = ASGITransport(app=app)
    sess = f"test_cancel_time_sess_{uuid.uuid4().hex[:6]}"

    # Set reminder to call son scheduled around 4 PM (15:59)
    from datetime import datetime, timedelta
    now = datetime.now()
    target_4pm = now.replace(hour=15, minute=59, second=0, microsecond=0)
    if target_4pm < now:
        target_4pm += timedelta(days=1)
    diff_secs = max(60, int((target_4pm - now).total_seconds()))

    set_reminder("call your son", delay_seconds=diff_secs, session_id=sess)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Check reminder is active
        res_list = await ac.get(f"/api/reminders/?session_id={sess}")
        assert res_list.status_code == 200
        assert res_list.json()["count"] == 1
        assert "call your son" in res_list.json()["reminders"][0]["text"]

        # Cancel by time reference: "cancel 4 pm reminder now"
        res_cancel = await ac.post("/api/chat", json={
            "session_id": sess,
            "text": "cancel 4 pm reminder now"
        })
        assert res_cancel.status_code == 200
        data = res_cancel.json()
        assert data["mode"] == "answer"
        speech = data["speech"].lower()
        assert "cancel" in speech
        assert "son" in speech or "reminder" in speech

        # Check active list is now 0
        res_after = await ac.get(f"/api/reminders/?session_id={sess}")
        assert res_after.status_code == 200
        assert res_after.json()["count"] == 0


@pytest.mark.asyncio
async def test_clear_conversation_voice_command_and_endpoint():
    """Verify that saying 'Sarah, clear entire conversation' or 'clear history'
    wipes conversation messages and references from the database."""
    transport = ASGITransport(app=app)
    sess = f"test_clear_conv_{uuid.uuid4().hex[:6]}"
    user_id = f"user_clear_{uuid.uuid4().hex[:6]}"

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Have multiple conversation turns
        await ac.post("/api/chat", json={
            "session_id": sess,
            "user_id": user_id,
            "text": "What is the boiling point of water?"
        })
        await ac.post("/api/chat", json={
            "session_id": sess,
            "user_id": user_id,
            "text": "Tell me a joke about robots."
        })

        # Verify messages exist in history
        res_hist = await ac.get(f"/api/chat/history?session_id={sess}")
        assert res_hist.status_code == 200
        assert res_hist.json()["count"] >= 2

        # 2. Spoken command to clear conversation
        res_clear = await ac.post("/api/chat", json={
            "session_id": sess,
            "user_id": user_id,
            "text": "Sarah, clear entire conversation"
        })
        assert res_clear.status_code == 200
        clear_data = res_clear.json()
        assert clear_data["mode"] == "answer"
        assert "cleared" in clear_data["speech"].lower()
        assert "conversation" in clear_data["speech"].lower() or "history" in clear_data["speech"].lower()

        # 3. Check history is now empty
        res_hist_after = await ac.get(f"/api/chat/history?session_id={sess}")
        assert res_hist_after.status_code == 200
        assert res_hist_after.json()["count"] == 0

        # 4. Check REST endpoint: POST /api/chat/clear
        # Add another message
        await ac.post("/api/chat", json={
            "session_id": sess,
            "user_id": user_id,
            "text": "Hello again"
        })
        res_hist_recheck = await ac.get(f"/api/chat/history?session_id={sess}")
        assert res_hist_recheck.json()["count"] >= 1

        # Clear via REST endpoint
        res_rest_clear = await ac.post("/api/chat/clear", json={
            "session_id": sess,
            "user_id": user_id,
            "clear_all": True
        })
        assert res_rest_clear.status_code == 200
        assert res_rest_clear.json()["status"] == "success"

        res_final = await ac.get(f"/api/chat/history?session_id={sess}")
        assert res_final.json()["count"] == 0
