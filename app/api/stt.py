"""STT API router providing audio transcription using Gemini Multimodal Audio and Faster-Whisper."""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
from app.stt import stt_service
from app.config import settings

router = APIRouter(prefix="/api/stt", tags=["stt"])


@router.post("")
@router.post("/")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe uploaded audio file using the configured STT engine (Gemini / Faster-Whisper)."""
    if not file:
        raise HTTPException(status_code=400, detail="No audio file uploaded.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")

    transcript = await stt_service.transcribe(
        content,
        mime_type=file.content_type,
        filename=file.filename
    )

    return {
        "text": transcript,
        "service": stt_service.service_name,
        "model": stt_service.model_name
    }
