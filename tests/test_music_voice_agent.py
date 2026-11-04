import pytest
from app.services.chat_service import chat_service
from app.schemas.contracts import ChatRequestContract
from app.gemini.tool_agent import tool_agent


@pytest.mark.asyncio
async def test_music_intent_detection():
    assert tool_agent.needs_tools("play a song") is True
    assert tool_agent.needs_tools("play music") is True
    assert tool_agent.needs_tools("can you please play some relaxing music") is True
    assert tool_agent.needs_tools("stop music") is True
    assert tool_agent.needs_tools("pause music") is True


@pytest.mark.asyncio
async def test_music_playback_voice_response():
    req = ChatRequestContract(text="play a song", session_id="test_music_session")
    resp = await chat_service.process_chat_turn(req)
    assert resp.mode == "answer"
    assert "playing" in resp.speech.lower()
    assert resp.music is not None
    assert resp.music.action == "play"
    assert resp.music.media_url == "/audio/relaxing_music.wav"
    assert resp.music.status == "playing"


@pytest.mark.asyncio
async def test_music_stop_voice_response():
    req = ChatRequestContract(text="stop music", session_id="test_music_session")
    resp = await chat_service.process_chat_turn(req)
    assert resp.mode == "answer"
    assert "stopped" in resp.speech.lower()
    assert resp.music is not None
    assert resp.music.action == "stop"

