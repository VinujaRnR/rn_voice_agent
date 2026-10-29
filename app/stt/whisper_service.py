"""Lightweight and highly accurate Speech-to-Text service using Faster-Whisper."""
import io
import os
import tempfile
import asyncio
from typing import Union, BinaryIO, Optional
try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

try:
    from app.config import settings
except ImportError:
    class DummySettings:
        whisper_model = "base.en"
        whisper_device = "cpu"
        whisper_compute_type = "int8"
        whisper_beam_size = 5
        whisper_initial_prompt = (
            "Sarah, turn on testing farm lights, room lights, kitchen lights, desk lamp, "
            "thermostat, Colombo, Sri Lanka, weather, temperature, schedule, status."
        )
    settings = DummySettings()


class WhisperSTTService:
    def __init__(
        self,
        model_size: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None
    ):
        self.model_size = model_size or settings.whisper_model
        self.device = device or settings.whisper_device
        self.compute_type = compute_type or settings.whisper_compute_type
        self._model: Optional[WhisperModel] = None

    @property
    def model(self) -> WhisperModel:
        if self._model is None:
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type
            )
        return self._model

    def transcribe_sync(
        self,
        audio_input: Union[bytes, BinaryIO, str],
        language: str = "en",
        beam_size: Optional[int] = None
    ) -> str:
        """Synchronously transcribe audio bytes, a file-like object, or a file path."""
        from app.stt.audio_preprocessor import audio_preprocessor
        from app.stt.accent_normalizer import normalize_accent_transcript

        # 1. Preprocess and acoustically condition audio before STT inference
        processed_input, resolved_mime = audio_preprocessor.preprocess(audio_input)

        effective_beam_size = beam_size or getattr(settings, "whisper_beam_size", 5)
        initial_prompt = getattr(
            settings,
            "whisper_initial_prompt",
            "Sarah, turn on testing farm lights, room lights, kitchen lights, desk lamp, thermostat, Colombo, Sri Lanka, weather, temperature, schedule, status."
        )

        # Determine file suffix based on resolved MIME
        suffix = ".wav" if resolved_mime == "audio/wav" else ".webm"

        # If processed_input is bytes or stream, save to a temporary file for PyAV/FFmpeg decoding
        temp_file_path = None
        try:
            if isinstance(processed_input, bytes):
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                    f.write(processed_input)
                    temp_file_path = f.name
                target = temp_file_path
            elif isinstance(processed_input, (io.BytesIO, io.BufferedReader)):
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                    f.write(processed_input.read())
                    temp_file_path = f.name
                target = temp_file_path
            else:
                target = processed_input

            segments, info = self.model.transcribe(
                target,
                language=language,
                beam_size=effective_beam_size,
                initial_prompt=initial_prompt,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=400),
                condition_on_previous_text=False
            )

            text_pieces = [segment.text.strip() for segment in segments]
            raw_result = " ".join(text_pieces).strip()
            return normalize_accent_transcript(raw_result)

        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass

    async def transcribe(
        self,
        audio_input: Union[bytes, BinaryIO, str],
        language: str = "en",
        beam_size: Optional[int] = None
    ) -> str:
        """Asynchronously transcribe audio using worker thread pool."""
        return await asyncio.to_thread(
            self.transcribe_sync,
            audio_input,
            language,
            beam_size
        )


whisper_service = WhisperSTTService()
