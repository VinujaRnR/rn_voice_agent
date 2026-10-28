import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.gemini.schemas import GeminiResponse, DeviceCommand


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "service": "rn_voice_assistant",
        "status": "healthy"
    }


@pytest.mark.asyncio
async def test_api_chat_endpoint_mocked():
    transport = ASGITransport(app=app)
    with patch(
        "app.api.chat.gemini_client.generate_response",
        new_callable=AsyncMock
    ) as mock_gemini:
        mock_gemini.return_value = GeminiResponse(
            mode="answer",
            speech="Hello, this is the RN Robots assistant.",
            command=None,
            missing_fields=[]
        )

        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/chat", json={
                "text": "Hello RN Robots",
                "session_id": "test_session_1"
            })

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "answer"
    assert data["speech"] == "Hello, this is the RN Robots assistant."
    assert data["command"] is None
    assert data["missing_fields"] == []


@pytest.mark.asyncio
async def test_api_chat_device_command_flow():
    transport = ASGITransport(app=app)
    with patch(
        "app.api.chat.gemini_client.generate_response",
        new_callable=AsyncMock
    ) as mock_gemini:
        mock_gemini.return_value = GeminiResponse(
            mode="device_command",
            speech=None,
            command=DeviceCommand(
                device_id="98a316e6b658",
                action="set_power",
                parameters={"state": "on"}
            ),
            missing_fields=[]
        )

        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/chat", json={
                "text": "Turn on testing farm lights",
                "session_id": "test_session_cmd"
            })

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "device_command"
    assert data["command"]["device_id"] == "98a316e6b658"
    assert data["command"]["action"] == "set_power"
    assert data["command"]["parameters"] == {"state": "on"}


@pytest.mark.asyncio
async def test_frontend_served():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/")
    assert response.status_code == 200
    assert "RN Voice Assistant" in response.text
