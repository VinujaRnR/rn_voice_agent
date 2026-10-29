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


def _create_test_wav_bytes(
    samples_list,
    sample_rate: int = 16000,
    n_channels: int = 1
) -> bytes:
    """Helper to create valid 16-bit PCM WAV bytes."""
    import io
    import wave
    import array

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        arr = array.array("h", samples_list)
        wf.writeframes(arr.tobytes())
    return buf.getvalue()


def test_audio_preprocessor_gain_normalization():
    """Verify that quiet speech audio is amplified to optimal target peak."""
    from app.stt.audio_preprocessor import AudioPreprocessor
    import wave
    import array
    import io

    # Generate quiet signal (peak = 2000, ~6% of full scale)
    quiet_samples = [2000, -2000, 1500, -1500] * 4000  # 1 second
    raw_wav = _create_test_wav_bytes(quiet_samples, 16000, 1)

    preprocessor = AudioPreprocessor(target_peak=0.90)
    processed_wav, resolved_mime = preprocessor.preprocess(raw_wav, mime_type="audio/wav")

    assert resolved_mime == "audio/wav"
    assert processed_wav != raw_wav

    with wave.open(io.BytesIO(processed_wav), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        samples = array.array("h")
        samples.frombytes(frames)
        peak = max(abs(s) for s in samples)
        # Target peak is 0.90 * 32767 = ~29490
        assert 28000 <= peak <= 30000


def test_audio_preprocessor_dc_offset_removal():
    """Verify that DC offset shifting the waveform is removed."""
    from app.stt.audio_preprocessor import AudioPreprocessor
    import array

    # 1000 DC offset bias added to waveform
    biased_samples = array.array("h", [1500, 500, 1200, 800] * 100)
    preprocessor = AudioPreprocessor()
    centered = preprocessor.remove_dc_offset(biased_samples)

    mean_after = sum(centered) / len(centered)
    assert abs(mean_after) < 1.0


def test_audio_preprocessor_silence_trimming():
    """Verify that excessive leading and trailing silence are trimmed."""
    from app.stt.audio_preprocessor import AudioPreprocessor
    import wave
    import io

    # 1 sec silence, 0.5 sec speech, 1 sec silence
    silence = [0] * 16000
    speech = [15000, -15000] * 4000
    all_samples = silence + speech + silence
    raw_wav = _create_test_wav_bytes(all_samples, 16000, 1)

    preprocessor = AudioPreprocessor(enable_silence_trim=True)
    processed_wav, _ = preprocessor.preprocess(raw_wav)

    with wave.open(io.BytesIO(processed_wav), "rb") as wf:
        n_frames = wf.getnframes()
        # Original was 40000 frames (2.5s). Trimmed should be around ~10000-15000 frames (< 1.5s)
        assert n_frames < 25000


def test_audio_preprocessor_stereo_to_mono():
    """Verify that stereo 2-channel audio is downmixed to mono."""
    from app.stt.audio_preprocessor import AudioPreprocessor
    import wave
    import io

    # Interleaved stereo: L, R, L, R...
    stereo_samples = [5000, 10000, -5000, -10000] * 2000
    raw_wav = _create_test_wav_bytes(stereo_samples, 16000, 2)

    preprocessor = AudioPreprocessor()
    processed_wav, _ = preprocessor.preprocess(raw_wav)

    with wave.open(io.BytesIO(processed_wav), "rb") as wf:
        assert wf.getnchannels() == 1

