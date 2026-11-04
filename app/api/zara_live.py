"""
WebSocket endpoint and runner for Zara Live - Gemini Live BIDI Voice AI.
Implements Google ADK Agent, Runner.run_live, StreamingMode.BIDI, and Aoede voice.
"""
import asyncio
import json
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from google.adk import Runner, Event
from google.adk.agents import Agent, RunConfig, LiveRequestQueue
from google.adk.agents.run_config import StreamingMode
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.config import settings
from app.security.auth import validate_ws_ticket
from app.gemini.tool_dispatcher import dispatch_tool_sync

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Sarah Live BIDI"])

SARAH_LIVE_SYSTEM_INSTRUCTION = """You are Sarah, an intelligent, empathetic live voice AI elderly care companion developed by RN Robots.
You communicate naturally with human-like conversation through real-time bidirectional audio.
You have native audio understanding and voice generation with prebuilt voice Aoede.
You support automatic language detection: identify whatever language the user speaks (English, Sinhala, Tamil, Spanish, French, Japanese, Mandarin, etc.) and seamlessly respond in the same language.
Keep responses concise, conversational, friendly, warm, and natural (1 to 2 sentences), ideal for real-time speech.
You help the resident with elderly care, companion conversation, health routines, smart devices, playing music, and daily questions.
You have access to tools to control smart devices, check weather, set reminders, and play music. Use them whenever requested."""

ZARA_LIVE_SYSTEM_INSTRUCTION = SARAH_LIVE_SYSTEM_INSTRUCTION


def control_smart_device(device_id: str, action: str = "turn_on") -> str:
    """Turn a home device on or off (e.g. room_lights, kitchen_lights, farm_lights, testing_farm_lights, desk_lamp, light_1, node 98a316e6b658).
    Args:
        device_id: Device identifier or name, e.g. 'room_lights', 'farm_lights', 'testing_farm_lights', 'desk_lamp', '98a316e6b658'
        action: 'turn_on' or 'turn_off'
    """
    try:
        res = dispatch_tool_sync("control_device", {"device_id": device_id, "action": action})
        return str(res.get("feedback") or res.get("status") or "Command dispatched to RN Hub.")
    except Exception as e:
        return f"Could not control device: {e}"


def list_smart_devices() -> str:
    """Retrieve status of all connected smart home devices in the household."""
    try:
        res = dispatch_tool_sync("list_devices", {})
        return str(res)
    except Exception as e:
        return f"Could not list devices: {e}"


def set_care_reminder(reminder_text: str, due_time: str = "soon") -> str:
    """Set a medication or care reminder for the resident.
    Args:
        reminder_text: What the reminder is for, e.g. 'take evening heart medicine'
        due_time: Time for the reminder, e.g. 'at 8 PM', 'in 15 minutes'
    """
    try:
        res = dispatch_tool_sync("set_reminder", {"text": reminder_text, "time": due_time})
        return str(res.get("message") or "Reminder successfully set.")
    except Exception as e:
        return f"Could not set reminder: {e}"


def check_local_weather(city: str = "Colombo") -> str:
    """Get the current weather and temperature for a city.
    Args:
        city: City name, e.g. 'Colombo', 'Sydney', 'Melbourne'
    """
    try:
        res = dispatch_tool_sync("get_weather", {"city": city})
        if "temperature" in res:
            return f"Weather in {res.get('city')}: {res.get('condition')}, {res.get('temperature')}, humidity {res.get('humidity')}."
        return str(res)
    except Exception as e:
        return f"Could not get weather: {e}"


def play_music(song_or_style: str = "relaxing music") -> str:
    """Play a music track or ambient relaxing sounds for the resident.
    Args:
        song_or_style: Name of song or music style, e.g. 'relaxing music', 'Elvis Presley', 'classical'
    """
    try:
        res = dispatch_tool_sync("control_music", {"action": "play", "query": song_or_style})
        return str(res.get("speech") or "Playing relaxing music.")
    except Exception as e:
        return f"Could not play music: {e}"


SARAH_LIVE_TOOLS = [
    control_smart_device,
    list_smart_devices,
    set_care_reminder,
    check_local_weather,
    play_music
]


def build_zara_agent(model_name: str) -> Agent:
    """Build Google ADK Agent configured for Sarah live persona."""
    return Agent(
        name="sarah_live_agent",
        model=model_name,
        instruction=SARAH_LIVE_SYSTEM_INSTRUCTION,
        tools=SARAH_LIVE_TOOLS
    )


def build_run_config() -> RunConfig:
    """Build ADK RunConfig enforcing BIDI streaming, Aoede voice, and dual transcription."""
    return RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config={"prebuilt_voice_config": {"voice_name": settings.gemini_live_voice or "Aoede"}}
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig()
    )


@router.websocket("/api/v1/sarah-live/ws")
@router.websocket("/api/v1/zara-live/ws")
async def zara_live_websocket(
    websocket: WebSocket,
    ticket: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None)
):
    """
    Real-time bidirectional WebSocket interface:
    - Input: Raw PCM 16-bit, 16 kHz audio chunks
    - Output: Raw PCM 16-bit, 24 kHz audio chunks (Aoede) + real-time transcription
    - Protocol: Google ADK Runner.run_live in StreamingMode.BIDI
    - Authentication: Short-lived JWT tickets
    """
    # 1. Validate Authentication via Ticket or Token
    auth_token = ticket or token
    user_id = "guest_user"
    role = "guest"
    household_id = None

    if auth_token:
        try:
            payload = validate_ws_ticket(auth_token)
            user_id = payload.get("sub", user_id)
            role = payload.get("role", role)
            household_id = payload.get("household_id")
        except Exception as auth_err:
            logger.warning(f"WebSocket ticket rejection: {auth_err}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired ticket")
            return
    else:
        logger.warning("WebSocket connection rejected: No authentication ticket provided.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication ticket required")
        return

    await websocket.accept()
    sess_id = session_id or f"zara_{user_id}_{int(asyncio.get_event_loop().time())}"

    # 2. Handshake confirmation
    await websocket.send_json({
        "type": "status",
        "state": "connected",
        "session_id": sess_id,
        "user_id": user_id,
        "role": role,
        "model": settings.gemini_live_model,
        "voice": settings.gemini_live_voice,
        "input_format": "audio/pcm;rate=16000",
        "output_format": "audio/pcm;rate=24000",
        "streaming_mode": "bidi"
    })

    # 3. Setup ADK Session and Queue
    session_service = InMemorySessionService()
    queue = LiveRequestQueue()
    config = build_run_config()

    primary_model = settings.gemini_live_model
    fallback_model = settings.gemini_live_fallback_model

    async def receive_from_client():
        """Receive PCM 16kHz audio or control messages from client and push to ADK queue."""
        try:
            while True:
                msg = await websocket.receive()
                if "bytes" in msg and msg["bytes"]:
                    # Raw PCM 16-bit, 16 kHz audio chunk from microphone
                    pcm_chunk = msg["bytes"]
                    blob = types.Blob(
                        mime_type=f"audio/pcm;rate={settings.gemini_live_input_sample_rate}",
                        data=pcm_chunk
                    )
                    queue.send_realtime(blob)
                elif "text" in msg and msg["text"]:
                    try:
                        data = json.loads(msg["text"])
                        mtype = data.get("type")
                        if mtype == "text":
                            txt = data.get("text", "")
                            if txt:
                                queue.send_content(types.Content(parts=[types.Part.from_text(text=txt)]))
                        elif mtype == "ping":
                            await websocket.send_json({"type": "pong"})
                        elif mtype == "interrupt":
                            # Client barge-in signal
                            pass
                    except Exception as json_err:
                        logger.debug(f"Ignored non-JSON text from client: {json_err}")
        except WebSocketDisconnect:
            logger.info(f"Zara Live client disconnected: {sess_id}")
        except Exception as e:
            logger.debug(f"Client receive task ended: {e}")
        finally:
            try:
                queue.close()
            except Exception:
                pass

    async def stream_from_runner():
        """Stream events, 24kHz audio, and dual transcriptions from ADK runner to client."""
        candidate_models = [primary_model, fallback_model, "gemini-2.5-flash-native-audio-latest", "gemini-3.1-flash-live-preview"]
        models_to_try = []
        for m in candidate_models:
            if m and m not in models_to_try:
                models_to_try.append(m)
        for idx, cur_model in enumerate(models_to_try):
            try:
                agent = build_zara_agent(cur_model)
                runner = Runner(
                    app_name="zara_live",
                    agent=agent,
                    session_service=session_service,
                    auto_create_session=True
                )
                logger.info(f"Starting Runner.run_live with model '{cur_model}' in BIDI mode...")
                async for event in runner.run_live(
                    user_id=user_id,
                    session_id=sess_id,
                    live_request_queue=queue,
                    run_config=config
                ):
                    # 1. Output Audio Stream Chunks (Raw PCM 16-bit, 24 kHz)
                    if event.content:
                        for part in event.content.parts or []:
                            if part.inline_data and part.inline_data.data:
                                await websocket.send_bytes(part.inline_data.data)
                            elif part.text:
                                await websocket.send_json({
                                    "type": "output_text",
                                    "text": part.text
                                })

                    # 2. Native Speech Recognition: User Input Transcription
                    if event.input_transcription:
                        await websocket.send_json({
                            "type": "input_transcription",
                            "text": event.input_transcription.text,
                            "finished": getattr(event.input_transcription, "finished", False)
                        })

                    # 3. Native Speech Generation: Zara Output Transcription
                    if event.output_transcription:
                        await websocket.send_json({
                            "type": "output_transcription",
                            "text": event.output_transcription.text,
                            "finished": getattr(event.output_transcription, "finished", False)
                        })

                    # 4. Turn & Barge-In Events
                    if event.interrupted:
                        await websocket.send_json({"type": "interrupted"})
                    if event.turn_complete:
                        await websocket.send_json({"type": "turn_complete"})

                # Success, no need for fallback
                break
            except Exception as stream_err:
                logger.warning(f"ADK runner stream error on '{cur_model}': {stream_err}")
                if idx < len(models_to_try) - 1:
                    logger.info(f"Switching to fallback model '{models_to_try[idx+1]}'...")
                    continue
                else:
                    try:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Zara live stream error: {stream_err}"
                        })
                    except Exception:
                        pass

    # Run client receive and model streaming tasks concurrently
    recv_task = asyncio.create_task(receive_from_client())
    stream_task = asyncio.create_task(stream_from_runner())

    done, pending = await asyncio.wait(
        [recv_task, stream_task],
        return_when=asyncio.FIRST_COMPLETED
    )

    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

