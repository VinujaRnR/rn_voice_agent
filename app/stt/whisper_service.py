"""Lightweight and highly accurate Speech-to-Text service using Faster-Whisper."""
import io
import os
import tempfile
import asyncio
from typing import Union, BinaryIO, Optional
from faster_whisper import WhisperModel
from app.config import settings


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
        beam_size: int = 1
    ) -> str:
        """Synchronously transcribe audio bytes, a file-like object, or a file path."""
        # If audio_input is bytes, save to a temporary file for PyAV/FFmpeg decoding
        temp_file_path = None
        try:
            if isinstance(audio_input, bytes):
                with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                    f.write(audio_input)
                    temp_file_path = f.name
                target = temp_file_path
            elif isinstance(audio_input, (io.BytesIO, io.BufferedReader)):
                with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                    f.write(audio_input.read())
                    temp_file_path = f.name
                target = temp_file_path
            else:
                target = audio_input

            segments, info = self.model.transcribe(
                target,
                language=language,
                beam_size=beam_size,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=400)
            )

            text_pieces = [segment.text.strip() for segment in segments]
            return " ".join(text_pieces).strip()

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
        beam_size: int = 1
    ) -> str:
        """Asynchronously transcribe audio using worker thread pool."""
        return await asyncio.to_thread(
            self.transcribe_sync,
            audio_input,
            language,
            beam_size
        )


whisper_service = WhisperSTTService()
