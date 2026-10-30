import io
import logging
from typing import Optional
from fastapi import APIRouter, Query, Response, HTTPException
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tts", tags=["TTS"])

# Pre-defined, strictly female high-fidelity neural voices
FEMALE_VOICES = {
    "jenny": "en-US-JennyNeural",
    "aria": "en-US-AriaNeural",
    "sonia": "en-GB-SoniaNeural",
    "neerja": "en-IN-NeerjaNeural",
    "natasha": "en-AU-NatashaNeural"
}

DEFAULT_FEMALE_VOICE = "en-US-JennyNeural"


@router.get("")
@router.get("/")
@router.post("")
@router.post("/")
@router.head("")
@router.head("/")
async def generate_speech(
    text: str = Query(..., description="Text to synthesize with Sarah's female voice"),
    voice: Optional[str] = Query("jenny", description="Voice profile: jenny, aria, sonia, neerja, natasha")
):
    """
    Generates high-definition female speech audio stream using Neural TTS.
    Guarantees 100% natural female voice across all operating systems and browsers.
    """
    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Text parameter cannot be empty.")

    selected_voice = FEMALE_VOICES.get((voice or "jenny").lower().strip(), DEFAULT_FEMALE_VOICE)

    try:
        import edge_tts
        communicate = edge_tts.Communicate(clean_text, selected_voice)
        audio_buffer = io.BytesIO()

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.write(chunk["data"])

        audio_bytes = audio_buffer.getvalue()
        if not audio_bytes:
            raise HTTPException(status_code=500, detail="TTS engine produced empty audio stream.")

        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "public, max-age=3600",
                "Content-Disposition": "inline; filename=\"sarah_speech.mp3\""
            }
        )
    except Exception as e:
        logger.error(f"TTS synthesis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to synthesize female speech: {str(e)}")


@router.get("/voices")
async def list_available_female_voices():
    """Returns the list of available high-fidelity female voices."""
    return {
        "status": "success",
        "default": "jenny",
        "voices": [
            {"id": "jenny", "name": "Sarah Natural (Jenny - US English)", "voice_id": "en-US-JennyNeural", "gender": "Female"},
            {"id": "aria", "name": "Sarah Professional (Aria - US English)", "voice_id": "en-US-AriaNeural", "gender": "Female"},
            {"id": "sonia", "name": "Sarah British (Sonia - UK English)", "voice_id": "en-GB-SoniaNeural", "gender": "Female"},
            {"id": "neerja", "name": "Sarah South Asian (Neerja - Indian English)", "voice_id": "en-IN-NeerjaNeural", "gender": "Female"},
            {"id": "natasha", "name": "Sarah Australian (Natasha - AU English)", "voice_id": "en-AU-NatashaNeural", "gender": "Female"}
        ]
    }

