"""Unit tests for STT services (Gemini Multimodal Audio and Faster-Whisper) and endpoints."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.stt.whisper_service import whisper_service
from app.stt.gemini_audio_service import gemini_audio_service, GeminiAudioSTTService
from app.stt import stt_service


@pytest.mark.asyncio
async def test_stt_endpoint():
    transport = ASGITransport(app=app)
    with patch.object(whisper_service, "transcribe", new_callable=AsyncMock) as mock_stt:
        mock_stt.return_value = "Sarah turn on testing farm lights"

        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            files = {"file": ("audio.webm", b"fake_audio_bytes", "audio/webm")}
            response = await ac.post("/api/stt", files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "Sarah turn on testing farm lights"
        assert data["service"] == "faster_whisper"


@pytest.mark.asyncio
async def test_chat_audio_endpoint():
    transport = ASGITransport(app=app)
    with patch.object(whisper_service, "transcribe", new_callable=AsyncMock) as mock_stt:
        mock_stt.return_value = "Sarah what is the weather?"

        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            files = {"file": ("voice.webm", b"audio_content", "audio/webm")}
            response = await ac.post("/api/chat/audio", files=files, data={"session_id": "test_audio_session"})

        assert response.status_code == 200
        data = response.json()
        assert data["transcript"] == "Sarah what is the weather?"
        assert data["response"]["mode"] == "answer"
        assert "weather" in data["response"]["speech"].lower()


def test_gemini_audio_mime_detection():
    """Verify MIME detection across supported audio formats."""
    # WAV
    wav_bytes = b"RIFF\x00\x00\x00\x00WAVE"
    assert GeminiAudioSTTService.detect_mime_type(wav_bytes) == "audio/wav"

    # WebM (EBML)
    webm_bytes = b"\x1a\x45\xdf\xa3\x00\x00\x00\x00\x00\x00\x00\x00"
    assert GeminiAudioSTTService.detect_mime_type(webm_bytes) == "audio/webm"

    # MP3 (ID3)
    mp3_bytes = b"ID3\x03\x00\x00\x00\x00\x00\x00\x00\x00"
    assert GeminiAudioSTTService.detect_mime_type(mp3_bytes) == "audio/mp3"

    # Filename fallback
    assert GeminiAudioSTTService.detect_mime_type(b"dummy", "voice.flac") == "audio/flac"
    assert GeminiAudioSTTService.detect_mime_type(b"dummy", "clip.ogg") == "audio/ogg"


@pytest.mark.asyncio
async def test_gemini_audio_stt_transcribe_mocked():
    """Verify GeminiAudioSTTService transcription execution and quote stripping."""
    service = GeminiAudioSTTService(api_key="mock_key")
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '"Sarah turn off the farm lights"'
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
    service._client = mock_client

    result = await service.transcribe(b"fake_audio_bytes", mime_type="audio/wav")
    assert result == "Sarah turn off the farm lights"


def test_accent_normalizer_phonetic_variations():
    """Verify that accent distortions are normalized to canonical domain words."""
    from app.stt.accent_normalizer import normalize_accent_transcript

    assert normalize_accent_transcript("sierra turn on testing firm lights") == "Sarah turn on testing farm lights"
    assert normalize_accent_transcript("what is the whether in columbo") == "what is the weather in Colombo"
    assert normalize_accent_transcript("serra tern off the fan lights") == "Sarah turn off the farm lights"
    assert normalize_accent_transcript("turn of the lights") == "turn off the lights"
    assert normalize_accent_transcript("sarah switch of the rum lights") == "Sarah switch off the room lights"

