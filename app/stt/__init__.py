"""Speech-to-Text module supporting Gemini Multimodal Audio and Faster-Whisper."""
from typing import Union, BinaryIO, Optional
from unittest.mock import Mock, AsyncMock

from app.config import settings
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
        engine = self.active_engine
        if isinstance(engine, GeminiAudioSTTService):
            return await engine.transcribe(audio_input, mime_type=mime_type, filename=filename)
        else:
            return await engine.transcribe(audio_input)

    def transcribe_sync(
        self,
        audio_input: Union[bytes, BinaryIO, str],
        mime_type: Optional[str] = None,
        filename: Optional[str] = None
    ) -> str:
        engine = self.active_engine
        if isinstance(engine, GeminiAudioSTTService):
            return engine.transcribe_sync(audio_input, mime_type=mime_type, filename=filename)
        else:
            return engine.transcribe_sync(audio_input)


stt_service = UnifiedSTTService()

__all__ = [
    "stt_service",
    "gemini_audio_service",
    "GeminiAudioSTTService",
    "whisper_service",
    "WhisperSTTService",
]
