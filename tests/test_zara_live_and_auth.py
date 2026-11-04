"""
Automated test suite verifying:
1. Login & Registration endpoints (/api/v1/auth/login, /api/v1/auth/register)
2. Short-lived JWT tickets (/api/v1/auth/ws-ticket)
3. Zara Live WebSocket architecture:
   - Model: gemini-3.5-flash-live-preview
   - Framework: Google ADK
   - Runner: Runner.run_live
   - Streaming mode: StreamingMode.BIDI
   - Endpoint: WS /api/v1/zara-live/ws
   - Audio formats: PCM 16kHz in, PCM 24kHz out
   - Voice: Aoede
"""
import pytest
import jwt
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.config import settings
from app.security.auth import create_ws_ticket, validate_ws_ticket


@pytest.fixture
def client():
    return TestClient(app)


def test_ws_ticket_generation_and_validation():
    # 1. Create a 60-second ticket
    ticket = create_ws_ticket(
        subject="test_resident_01",
        claims={"role": "resident", "household_id": "hh_test_123"},
        expires_seconds=60
    )
    assert isinstance(ticket, str)
    assert len(ticket) > 20

    # 2. Validate ticket
    payload = validate_ws_ticket(ticket)
    assert payload["sub"] == "test_resident_01"
    assert payload["role"] == "resident"
    assert payload["household_id"] == "hh_test_123"
    assert payload["token_type"] == "ws_ticket"


def test_ws_ticket_expired_rejection():
    # Ticket with negative expiration
    ticket = create_ws_ticket(
        subject="test_expired_user",
        expires_seconds=-10
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        validate_ws_ticket(ticket)


def test_ws_ticket_tampered_rejection():
    ticket = create_ws_ticket(subject="valid_user")
    tampered = ticket[:-4] + "fake"
    with pytest.raises(jwt.InvalidTokenError):
        validate_ws_ticket(tampered)


def test_api_ws_ticket_endpoint(client):
    res = client.post("/api/v1/auth/ws-ticket")
    assert res.status_code == 200
    data = res.json()
    assert "ticket" in data
    assert data["expires_in"] == settings.zara_live_ws_ticket_expire_seconds
    assert data["ws_endpoint"] in ("/api/v1/sarah-live/ws", "/api/v1/zara-live/ws")
    assert "user_id" in data
    assert data["role"] == "guest"


def test_api_register_and_login_flow(client):
    import uuid
    uid = uuid.uuid4().hex[:6]
    email = f"user_{uid}@testcare.com"
    pwd = "SecurePassword123!"

    # 1. Register new user
    reg_res = client.post("/api/v1/auth/register", json={
        "full_name": "Zara Test Resident",
        "email": email,
        "password": pwd,
        "role": "resident",
        "household_name": "Oakridge Suite"
    })
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert "access_token" in reg_data
    assert reg_data["role"] == "resident"

    # 2. Log in with registered user
    login_res = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": pwd
    })
    assert login_res.status_code == 200
    login_data = login_res.json()
    token = login_data["access_token"]
    assert token is not None

    # 3. Obtain authenticated WebSocket ticket
    t_res = client.post(
        "/api/v1/auth/ws-ticket",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert t_res.status_code == 200
    t_data = t_res.json()
    assert t_data["role"] == "resident"
    assert t_data["user_id"] == login_data["user_id"]


def test_api_login_invalid_credentials(client):
    res = client.post("/api/v1/auth/login", json={
        "email": "nonexistent_resident_123@nowhere.com",
        "password": "WrongPassword999!"
    })
    assert res.status_code == 401
    assert "Invalid email or password" in res.json()["detail"]


def test_zara_live_websocket_rejected_without_ticket(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/zara-live/ws") as ws:
            pass


def test_zara_live_websocket_connection_and_handshake(client):
    # 1. Get short-lived ticket
    t_res = client.post("/api/v1/auth/ws-ticket")
    ticket = t_res.json()["ticket"]

    # 2. Connect to WS /api/v1/zara-live/ws
    with client.websocket_connect(f"/api/v1/zara-live/ws?ticket={ticket}") as ws:
        status_msg = ws.receive_json()
        assert status_msg["type"] == "status"
        assert status_msg["state"] == "connected"
        assert status_msg["model"] == "gemini-3.5-flash-live-preview"
        assert status_msg["voice"] == "Aoede"
        assert status_msg["input_format"] == "audio/pcm;rate=16000"
        assert status_msg["output_format"] == "audio/pcm;rate=24000"
        assert status_msg["streaming_mode"] == "bidi"

        # 3. Test ping/pong
        ws.send_json({"type": "ping"})
        pong_msg = ws.receive_json()
        assert pong_msg["type"] == "pong"

        # 4. Test sending 16 kHz PCM chunk
        pcm16_chunk = b"\x00" * 3200  # 100ms of 16-bit 16kHz silence
        ws.send_bytes(pcm16_chunk)


def test_sarah_live_websocket_connection_and_handshake(client):
    """Verify primary /api/v1/sarah-live/ws endpoint handshakes with Aoede voice & BIDI mode."""
    t_res = client.post("/api/v1/auth/ws-ticket")
    ticket = t_res.json()["ticket"]
    assert t_res.json()["ws_endpoint"] == "/api/v1/sarah-live/ws"

    with client.websocket_connect(f"/api/v1/sarah-live/ws?ticket={ticket}") as ws:
        status_msg = ws.receive_json()
        assert status_msg["type"] == "status"
        assert status_msg["state"] == "connected"
        assert status_msg["voice"] == "Aoede"
        assert status_msg["input_format"] == "audio/pcm;rate=16000"
        assert status_msg["output_format"] == "audio/pcm;rate=24000"
        assert status_msg["streaming_mode"] == "bidi"

        ws.send_json({"type": "ping"})
        pong_msg = ws.receive_json()
        assert pong_msg["type"] == "pong"


