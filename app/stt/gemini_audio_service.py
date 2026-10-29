"""Gemini Multimodal Audio Speech-to-Text Service.

Provides cloud-based, highly accurate speech recognition across all accents,
dialects, and noisy environments with zero local CPU/RAM compute overhead.
"""
import io
import os
import logging
from typing import Union, BinaryIO, Optional, Any
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

try:
    from app.config import settings
except ImportError:
    class DummySettings:
        gemini_api_key = ""
        gemini_model = "gemini-3.5-flash-lite"
    settings = DummySettings()

from app.stt.accent_normalizer import normalize_accent_transcript

logger = logging.getLogger(__name__)

TRANSCRIPTION_INSTRUCTION = (
    "You are an expert Speech-to-Text engine for the RN Robots 'Sarah' AI voice assistant. "
    "The speaker is speaking English, frequently with an international, Sri Lankan, South Asian, or accented cadence. "
    "Transcribe all speech accurately and verbatim in standard English, correcting for accent-induced phoneme distortions "
    "(such as non-rhotic vowels, dental stops, and regional intonations).\n\n"
    "CRITICAL DOMAIN VOCABULARY:\n"
    "- Wake words: 'Sarah' (also sounds like 'Sera', 'Serah', 'Sahra', 'Saira', 'Zarah', 'Sara')\n"
    "- Smart Devices: 'Testing Farm Lights' (may sound like 'testing fan lights' or 'testing form lights'), "
    "'Room Lights', 'Kitchen Lights', 'Desk Lamp', 'Thermostat', 'Robot Vacuum'\n"
    "- Locations: 'Colombo', 'Sri Lanka', 'Tokyo', 'Kandy', 'Galle'\n"
    "- Commands: 'turn on', 'turn off', 'switch on', 'switch off', 'schedule', 'status', 'weather', 'rain', 'forecast', 'temperature', 'restaurants', 'dinner'\n\n"
    "RULES:\n"
    "1. Output ONLY the raw transcribed plain text. Do not add markdown, quotes, notes, or explanations.\n"
    "2. If the audio is silent, background noise, or unintelligible, output an empty string."
)


class GeminiAudioSTTService:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model_name = model or settings.gemini_model or "gemini-3.5-flash-lite"
        self._client: Optional[Any] = None
        self.service_name = "gemini_multimodal_audio"

    @property
    def client(self) -> Optional[Any]:
        if self._client is None and self.api_key:
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Gemini Client for STT: {e}")
                self._client = None
        return self._client

    @staticmethod
    def detect_mime_type(audio_bytes: bytes, filename: Optional[str] = None) -> str:
        """Detect MIME type from file magic bytes or filename extension."""
        if len(audio_bytes) >= 12:
            if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
                return "audio/wav"
            if audio_bytes[:4] == b"\x1a\x45\xdf\xa3":
                return "audio/webm"
            if audio_bytes[:3] == b"ID3" or (audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0):
                return "audio/mp3"
            if audio_bytes[:4] == b"OggS":
                return "audio/ogg"
            if audio_bytes[:4] == b"fLaC":
                return "audio/flac"

        if filename:
            lower = filename.lower()
            if lower.endswith(".wav"):
                return "audio/wav"
            if lower.endswith(".mp3"):
                return "audio/mp3"
            if lower.endswith(".ogg"):
                return "audio/ogg"
            if lower.endswith(".flac"):
                return "audio/flac"
            if lower.endswith(".m4a") or lower.endswith(".aac"):
                return "audio/aac"
            if lower.endswith(".webm"):
                return "audio/webm"

        return "audio/webm"

    async def transcribe(
        self,
        audio_input: Union[bytes, BinaryIO, str],
        mime_type: Optional[str] = None,
        filename: Optional[str] = None
    ) -> str:
        """Transcribe audio bytes or file asynchronously using Gemini Multimodal Audio."""
        # 1. Extract bytes
        if isinstance(audio_input, bytes):
            audio_bytes = audio_input
        elif isinstance(audio_input, (io.BytesIO, io.BufferedReader)):
            audio_bytes = audio_input.read()
        elif isinstance(audio_input, str) and os.path.exists(audio_input):
            with open(audio_input, "rb") as f:
                audio_bytes = f.read()
            if not filename:
                filename = os.path.basename(audio_input)
        else:
            return ""

        if not audio_bytes:
            return ""

        # 2. Acoustically condition, filter, and normalize audio before STT inference
        from app.stt.audio_preprocessor import audio_preprocessor
        processed_audio, detected_mime = audio_preprocessor.preprocess(
            audio_bytes,
            mime_type=mime_type,
            filename=filename
        )
        if isinstance(processed_audio, bytes):
            audio_bytes = processed_audio

        # 3. Determine MIME type
        resolved_mime = detected_mime or mime_type or self.detect_mime_type(audio_bytes, filename)

        # 4. If client not available, fallback to faster_whisper
        if not self.client:
            logger.warning("Gemini STT client unavailable, falling back to local Faster-Whisper.")
            from app.stt.whisper_service import whisper_service
            return await whisper_service.transcribe(audio_bytes)

        # 4. Transcribe via Gemini Multimodal Audio API
        try:
            audio_part = types.Part.from_bytes(
                data=audio_bytes,
                mime_type=resolved_mime
            )

            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=[audio_part, TRANSCRIPTION_INSTRUCTION],
                config=types.GenerateContentConfig(
                    temperature=0.0
                )
            )

            if response and response.text:
                clean_text = response.text.strip()
                # If model returned EMPTY or silence marker
                if clean_text.upper() in ["EMPTY", "EMPTY.", "[SILENCE]", "NO SPEECH DETECTED"]:
                    return ""
                # Strip wrapping quotes if Gemini added any
                if clean_text.startswith('"') and clean_text.endswith('"') and len(clean_text) > 2:
                    clean_text = clean_text[1:-1].strip()
                return normalize_accent_transcript(clean_text)

            return ""

        except Exception as e:
            logger.error(f"Gemini STT transcription error: {e}. Falling back to Faster-Whisper.")
            try:
                from app.stt.whisper_service import whisper_service
                return await whisper_service.transcribe(audio_bytes)
            except Exception as fe:
                logger.error(f"Faster-Whisper fallback failed: {fe}")
                return ""

    def transcribe_sync(
        self,
        audio_input: Union[bytes, BinaryIO, str],
        mime_type: Optional[str] = None,
        filename: Optional[str] = None
    ) -> str:
        """Synchronously transcribe audio."""
        import asyncio
        return asyncio.run(self.transcribe(audio_input, mime_type=mime_type, filename=filename))


gemini_audio_service = GeminiAudioSTTService()
