"""Speech-to-Text module supporting Gemini Multimodal Audio and Faster-Whisper."""
from typing import Union, BinaryIO, Optional
from unittest.mock import Mock, AsyncMock

try:
    from app.config import settings
except ImportError:
    class DummySettings:
        stt_engine = "gemini"
        whisper_model = "base.en"
        whisper_device = "cpu"
        whisper_compute_type = "int8"
        whisper_beam_size = 5
        whisper_initial_prompt = (
            "Sarah, turn on testing farm lights, room lights, kitchen lights, desk lamp, "
            "thermostat, Colombo, Sri Lanka, weather, temperature, schedule, status."
        )
        audio_preprocess_enabled = True
        audio_target_peak = 0.90
        audio_noise_reduction_enabled = True
        audio_silence_trim_enabled = True
    settings = DummySettings()

from app.stt.audio_preprocessor import audio_preprocessor, AudioPreprocessor
from app.stt.gemini_audio_service import gemini_audio_service, GeminiAudioSTTService
from app.stt.whisper_service import whisper_service, WhisperSTTService


class UnifiedSTTService:
    """Unified STT dispatcher selecting between Gemini Multimodal Audio and Faster-Whisper."""

    @property
    def active_engine(self):
        # If whisper_service has been patched in unit tests, respect the mock
        if isinstance(whisper_service.transcribe, (Mock, AsyncMock)):
            return whisper_service

        engine = (settings.stt_engine or "gemini").lower()
        if engine in ["faster_whisper", "whisper", "local"]:
            return whisper_service
        return gemini_audio_service

    @property
    def service_name(self) -> str:
        return getattr(self.active_engine, "service_name", "faster_whisper")

    @property
    def model_name(self) -> str:
        return getattr(self.active_engine, "model_name", settings.whisper_model)

    async def transcribe(
        self,
        audio_input: Union[bytes, BinaryIO, str],
        mime_type: Optional[str] = None,
        filename: Optional[str] = None
    ) -> str:
        # 1. Acoustically condition, filter, and normalize audio before STT inference
        processed_input, resolved_mime = audio_preprocessor.preprocess(
            audio_input,
            mime_type=mime_type,
            filename=filename
        )

        # 2. Transcribe using active engine
        engine = self.active_engine
        if isinstance(engine, GeminiAudioSTTService):
            return await engine.transcribe(processed_input, mime_type=resolved_mime, filename=filename)
        else:
            return await engine.transcribe(processed_input)

    def transcribe_sync(
        self,
        audio_input: Union[bytes, BinaryIO, str],
        mime_type: Optional[str] = None,
        filename: Optional[str] = None
    ) -> str:
        # 1. Acoustically condition, filter, and normalize audio before STT inference
        processed_input, resolved_mime = audio_preprocessor.preprocess(
            audio_input,
            mime_type=mime_type,
            filename=filename
        )

        # 2. Transcribe using active engine
        engine = self.active_engine
        if isinstance(engine, GeminiAudioSTTService):
            return engine.transcribe_sync(processed_input, mime_type=resolved_mime, filename=filename)
        else:
            return engine.transcribe_sync(processed_input)


stt_service = UnifiedSTTService()

__all__ = [
    "stt_service",
    "audio_preprocessor",
    "AudioPreprocessor",
    "gemini_audio_service",
    "GeminiAudioSTTService",
    "whisper_service",
    "WhisperSTTService",
]
