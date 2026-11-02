import re
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from app.gemini.client import GeminiClient
from app.gemini.schemas import GeminiResponse, DeviceCommand
from app.conversation.manager import ConversationManager
from app.stt import stt_service, whisper_service
from app.gemini.tool_agent import tool_agent
from app.commands.device_registry import device_registry
from app.tools.device_control import execute_device_command

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Singleton instances
conversation_manager = ConversationManager()
gemini_client = GeminiClient()


class ChatRequest(BaseModel):
    text: Optional[str] = None
    message: Optional[str] = None
    session_id: Optional[str] = Field(default="default_session")
    user_id: Optional[str] = Field(default="default_user")
    enforce_wake_standby: Optional[bool] = False

    def get_query(self) -> str:
        return (self.text or self.message or "").strip()


@router.post("", response_model=GeminiResponse)
@router.post("/", response_model=GeminiResponse)
async def chat_endpoint(request: ChatRequest):
    user_query = request.get_query()
    session_id = request.session_id or "default_session"
    user_id = request.user_id or "default_user"

    if not user_query:
        return GeminiResponse(
            mode="answer",
            speech="I did not catch that. Please speak or type your request again.",
            command=None,
            missing_fields=[]
        )

    # 1. Fetch conversation history for this session
    history = conversation_manager.get_history(session_id)

    # 2. Record user query in SQLite database with SHA-256 cryptographic hashes for future reference
    conversation_manager.add_user_message(session_id, user_query, user_id=user_id)

    # 3. Handle session wake/sleep states
    raw_query = user_query.strip()
    has_wake = conversation_manager.has_wake_word(raw_query)

    # Wake-word only: "Sarah", "Hey Sarah"
    if conversation_manager.is_wake_word_only(raw_query):
        conversation_manager.wake_session(session_id)
        gemini_response = GeminiResponse(
            mode="answer",
            speech="Hello! I'm Sarah. I'm listening, what can I do for you?",
            command=None,
            missing_fields=[]
        )
    # Sleep intent: "go to sleep", "sleep", "stop listening"
    elif raw_query.lower() in ["go to sleep", "sleep", "turn off", "power down", "good night", "stop listening"]:
        conversation_manager.sleep_session(session_id)
        gemini_response = GeminiResponse(
            mode="answer",
            speech="Good night. Say 'Sarah' whenever you need me again.",
            command=None,
            missing_fields=[]
        )
    # Clear conversation / history command
    elif bool(re.search(
        r"\b(?:clear|delete|wipe|reset|erase)\s+(?:the\s+|all\s+|my\s+|entire\s+)?(?:history|conversation|chat|messages)\b",
        re.sub(r"^(?:(?:could|can|would|will)\s+you\s+)?(?:please\s+)?(?:sarah\s*,?\s*)?", "", raw_query.lower()).strip(),
        re.IGNORECASE
    )) or re.sub(r"^(?:(?:could|can|would|will)\s+you\s+)?(?:please\s+)?(?:sarah\s*,?\s*)?", "", raw_query.lower()).strip() in [
        "clear history", "clear conversation", "clear entire conversation",
        "clear all conversation", "reset conversation", "delete history", "delete conversation"
    ]:
        from app.context.memory import conversation_memory
        clean_c = re.sub(r"^(?:(?:could|can|would|will)\s+you\s+)?(?:please\s+)?(?:sarah\s*,?\s*)?", "", raw_query.lower()).strip()
        clear_entire = any(w in clean_c for w in ["entire", "all", "everything"])
        conversation_manager.storage.clear_conversation_history(session_id=session_id, user_id=user_id, clear_all=clear_entire)
        conversation_memory.clear_memory(session_id=session_id, clear_all=clear_entire)
        feedback = "I've cleared the entire conversation history." if clear_entire else "I've cleared your conversation history."
        return GeminiResponse(
            mode="answer",
            speech=feedback,
            command=None,
            missing_fields=[]
        )
    # Standby enforcement
    elif request.enforce_wake_standby and not has_wake and not conversation_manager.is_session_awake(session_id):
        gemini_response = GeminiResponse(
            mode="answer",
            speech="I'm currently in sleep mode. Please say 'Sarah' to wake me up.",
            command=None,
            missing_fields=[]
        )
    else:
        # Update session activity
        if has_wake:
            conversation_manager.wake_session(session_id)
        else:
            conversation_manager.touch_session(session_id)

        # Check if user is answering a pending reminder clarification (task or recurrence)
        gemini_response = None
        is_answering_pending_reminder = False
        is_answering_recurrence = False
        pending_action_data = conversation_manager.get_pending_action(session_id)
        if pending_action_data and pending_action_data.get("action") == "set_reminder_recurrence":
            clean_ans = user_query.lower().strip()
            rec_match = None
            if re.search(r"\b(?:daily|every\s+day|everyday)\b", clean_ans):
                rec_match = "daily"
            elif re.search(r"\b(?:weekly|every\s+week)\b", clean_ans):
                rec_match = "weekly"
            elif re.search(r"\b(?:monthly|every\s+month)\b", clean_ans):
                rec_match = "monthly"
            elif re.search(r"\bcustom\b", clean_ans):
                rec_match = "custom"
            elif re.search(r"\b(?:only\s+for\s+that\s+day|only\s+that\s+day|only\s+today|just\s+today|just\s+for\s+today|today\s+only|once|that\s+day|today|for\s+that\s+day)\b", clean_ans):
                rec_match = "once"

            if rec_match:
                is_answering_pending_reminder = True
                is_answering_recurrence = True
                from app.tools.reminders import update_reminder_recurrence
                from app.gemini.schemas import ReminderSpec
                rem_id = pending_action_data.get("parameters", {}).get("reminder_id")
                upd = update_reminder_recurrence(rem_id, rec_match, session_id=session_id)
                conversation_manager.resolve_pending_action(session_id)
                gemini_response = GeminiResponse(
                    mode="answer",
                    speech=upd.get("feedback", f"Got it, I've set this reminder for {rec_match}."),
                    command=None,
                    missing_fields=[],
                    reminder=ReminderSpec(
                        action_type="set",
                        task=pending_action_data.get("parameters", {}).get("task"),
                        target_time=pending_action_data.get("parameters", {}).get("target_time"),
                        recurrence=rec_match
                    )
                )
            elif clean_ans in ["cancel", "stop", "never mind", "abort"]:
                is_answering_pending_reminder = True
                is_answering_recurrence = True
                conversation_manager.cancel_pending_action(session_id)
                gemini_response = GeminiResponse(
                    mode="answer",
                    speech="Okay, cancelled.",
                    command=None,
                    missing_fields=[]
                )
            else:
                conversation_manager.cancel_pending_action(session_id)

        elif pending_action_data and pending_action_data.get("action") == "set_reminder_task":
            clean_ans = user_query.strip()
            if clean_ans.lower() in ["cancel", "stop", "never mind", "abort"]:
                is_answering_pending_reminder = True
                conversation_manager.cancel_pending_action(session_id)
                gemini_response = GeminiResponse(
                    mode="answer",
                    speech="Okay, cancelled.",
                    command=None,
                    missing_fields=[]
                )
            else:
                from app.conversation.manager import is_general_question_or_chitchat
                is_topic_switch = (
                    is_general_question_or_chitchat(user_query) or
                    any(w in clean_ans.lower() for w in ["turn on", "turn off", "switch on", "switch off", "weather", "forecast", "what is", "who is", "why is", "tell me about"])
                )
                if not is_topic_switch:
                    is_answering_pending_reminder = True
                    from app.tools.reminders import parse_reminder_expression, is_incomplete_reminder_task, set_reminder
                    from app.gemini.schemas import ReminderSpec
                    params = pending_action_data.get("parameters", {})
                    partial_verb = (params.get("partial_verb") or "").strip()
                    time_label = params.get("time_label")

                    combined_query = clean_ans
                    if partial_verb and not clean_ans.lower().startswith(partial_verb.lower()):
                        combined_query = f"{partial_verb} {clean_ans}"
                    if time_label and not any(t in clean_ans.lower() for t in ["am", "pm", "o'clock", "oclock", "minutes", "mins", "hours", "secs"]):
                        combined_query = f"{combined_query} {time_label}"

                    parsed = parse_reminder_expression(combined_query)
                    is_inc, verb = is_incomplete_reminder_task(parsed["text"], combined_query)
                    if is_inc:
                        from app.tools.reminders import generate_reminder_clarification_question
                        speech = generate_reminder_clarification_question(verb or partial_verb, parsed["text"], parsed.get("delay_label") if parsed.get("is_clock_time") else None)
                        gemini_response = GeminiResponse(
                            reasoning="Reminder task still incomplete. Requesting clarification.",
                            mode="clarify",
                            speech=speech,
                            command=None,
                            missing_fields=["task", "target_time"]
                        )
                    else:
                        rec = parsed.get("recurrence")
                        sr = set_reminder(
                            text=parsed["text"],
                            delay_seconds=parsed["delay_seconds"],
                            recurrence=rec,
                            session_id=session_id
                        )
                        rem_fb = sr.get("feedback")
                        if rec is None:
                            if not any(w in rem_fb.lower() for w in ["daily", "weekly", "monthly", "custom", "only for that day", "only that day"]):
                                rec_q = "Would you like this reminder for daily, weekly, monthly, custom, or only for that day?"
                                speech = f"{rem_fb} {rec_q}"
                            else:
                                speech = rem_fb
                            conversation_manager.save_pending_action(
                                session_id=session_id,
                                action="set_reminder_recurrence",
                                parameters={
                                    "reminder_id": sr["reminder_id"],
                                    "task": sr.get("text"),
                                    "target_time": sr.get("due_at")
                                },
                                missing_fields=["recurrence"]
                            )
                        else:
                            speech = rem_fb
                            conversation_manager.resolve_pending_action(session_id)

                        gemini_response = GeminiResponse(
                            mode="answer",
                            speech=speech,
                            command=None,
                            missing_fields=[],
                            reminder=ReminderSpec(
                                action_type="set",
                                task=sr.get("text"),
                                target_time=sr.get("due_at"),
                                delay_minutes=round(sr.get("delay_seconds", 600) / 60, 1),
                                recurrence=rec
                            ),
                            reminder_already_executed=True
                        )
                else:
                    conversation_manager.cancel_pending_action(session_id)

        # Primary Path: Use Gemini LLM reasoning whenever Gemini API is configured
        has_gemini = bool(gemini_client.api_key and not gemini_client.api_key.startswith("YOUR_API_KEY"))

        if gemini_response is None and has_gemini:
            try:
                if tool_agent.needs_tools(user_query, session_id=session_id):
                    gemini_response = await tool_agent.run(user_query, session_id)
                else:
                    prompt = conversation_manager.build_clarification_prompt(session_id, user_query)
                    gemini_response = await gemini_client.generate_response(
                        prompt=prompt,
                        conversation_history=history,
                        session_id=session_id
                    )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Gemini API primary invocation fallback: {e}")
                gemini_response = None

        # Fallback Path: Offline deterministic resolver if Gemini is unconfigured or failed
        if gemini_response is None:
            local_resolution = conversation_manager.resolve_intent_with_context(
                session_id,
                user_query,
                enforce_wake_standby=False
            )
            if local_resolution:
                gemini_response = local_resolution
            elif tool_agent.needs_tools(user_query, session_id=session_id):
                gemini_response = await tool_agent.run(user_query, session_id)
            else:
                prompt = conversation_manager.build_clarification_prompt(session_id, user_query)
                gemini_response = await gemini_client.generate_response(
                    prompt=prompt,
                    conversation_history=history,
                    session_id=session_id
                )
        if gemini_response is None:
            gemini_response = GeminiResponse(
                mode="answer",
                speech="I'm sorry, I'm having trouble processing your request right now. Please try again.",
                command=None,
                missing_fields=[]
            )

    # If answering a pending device clarification with an unknown device name, preserve clarify mode
    pending_before = conversation_manager.get_pending_action(session_id)
    if pending_before and "device_id" in pending_before.get("missing_fields", []):
        from app.conversation.manager import is_general_question_or_chitchat
        if gemini_response.mode == "answer" and not gemini_response.command and not getattr(gemini_response, "reminder", None):
            if not is_general_question_or_chitchat(user_query):
                gemini_response.mode = "clarify"
                gemini_response.missing_fields = ["device_id"]
        elif gemini_response.mode == "device_command" and gemini_response.command:
            # Check if user named an unrecognized device with unfamiliar qualifiers (e.g. "kitchen rooftop patio")
            q_words = [w for w in user_query.lower().split() if w not in ["the", "a", "an", "lights", "light", "please", "on", "off", "turn"]]
            if any(w in ["rooftop", "patio", "balcony", "attic", "basement", "backyard", "garage"] for w in q_words):
                gemini_response = GeminiResponse(
                    mode="clarify",
                    speech=f"I couldn't find a device matching '{user_query}'. Which lights did you want, like the room lights, kitchen lights, or desk lamp?",
                    command=None,
                    missing_fields=["device_id"]
                )

    # Update pending actions based on Gemini response
    if gemini_response.mode == "clarify":
        is_reminder_clarify = any(f in (gemini_response.missing_fields or []) for f in ["task", "target_time", "recurrence"])
        curr_pending = conversation_manager.get_pending_action(session_id)
        if not is_reminder_clarify and not (curr_pending and curr_pending.get("action") in ["set_reminder_task", "set_reminder_recurrence"]):
            action = "set_power" if "light" in user_query.lower() else "unknown"
            state = "off" if "off" in user_query.lower() else "on"
            conversation_manager.save_pending_action(
                session_id=session_id,
                action=action,
                parameters={"state": state},
                missing_fields=gemini_response.missing_fields or ["device_id"]
            )
    elif gemini_response.mode == "device_command":
        if gemini_response.is_executable():
            cmd_obj = gemini_response.command

            # Enrich command fields from device registry if not already fully populated
            resolved_dev = (
                device_registry.resolve_device(cmd_obj.device_id)
                or device_registry.normalize_device_id(cmd_obj.device_id)
            )
            sub_dev = device_registry.get_sub_device(resolved_dev or cmd_obj.device_id, cmd_obj.device_id)
            if not sub_dev and resolved_dev:
                dev_meta = device_registry.get_device(resolved_dev) or {}
                connected = dev_meta.get("connected_devices", [])
                if len(connected) == 1:
                    sub_dev = connected[0]

            if sub_dev:
                if not cmd_obj.channel_key:
                    cmd_obj.channel_key = sub_dev.get("channel_key") or f"relay:{sub_dev.get('type', 'light')}"
                if not cmd_obj.device_type:
                    cmd_obj.device_type = sub_dev.get("device_type") or sub_dev.get("type", "light")
                if not cmd_obj.device_number:
                    cmd_obj.device_number = sub_dev.get("device_number") or 1
                if not cmd_obj.device_name:
                    cmd_obj.device_name = sub_dev.get("device_name") or sub_dev.get("name")
                if cmd_obj.device_id == resolved_dev and sub_dev.get("device_id"):
                    cmd_obj.device_id = sub_dev.get("device_id")

            parent_dev = device_registry.get_device(resolved_dev or cmd_obj.device_id) or {}
            available_actions = parent_dev.get("actions") or parent_dev.get("allowed_actions") or []
            desired_on = (
                (cmd_obj.action in ["turn_on", "LIGHT_ON"])
                or (hasattr(cmd_obj.parameters, "get") and cmd_obj.parameters.get("state") == "on")
                or (isinstance(cmd_obj.parameters, dict) and cmd_obj.parameters.get("state") == "on")
                or ("on" in str(cmd_obj.actions).lower())
            )

            if "LIGHT_ON" in available_actions or "LIGHT_OFF" in available_actions:
                cmd_obj.actions = "LIGHT_ON" if desired_on else "LIGHT_OFF"
                cmd_obj.action = cmd_obj.actions
                from app.gemini.schemas import DeviceParameters
                cmd_obj.params = DeviceParameters()
                cmd_obj.parameters = {}
            elif "set_power" in available_actions or cmd_obj.device_id in ["room_lights", "kitchen_lights", "98a316e6b658", "desk_lamp"]:
                cmd_obj.actions = "set_power"
                cmd_obj.action = "set_power"
                cmd_obj.params = {"state": "on" if desired_on else "off"}
                cmd_obj.parameters = {"state": "on" if desired_on else "off"}

            if (resolved_dev == "98a316e6b658" or cmd_obj.device_id == "98a316e6b658"):
                history_msgs = conversation_manager.get_history(session_id)
                history_text = " ".join([m.get("content", "") for m in history_msgs]).lower()
                if "farm" in user_query.lower() or "farm" in history_text:
                    gemini_response.speech = "Sending the command to RN Hub."

            exec_result = execute_device_command(
                device_id=cmd_obj.device_id,
                action=cmd_obj.action,
                parameters=cmd_obj.parameters,
                session_id=session_id,
                command_obj=cmd_obj
            )
            if exec_result.get("command_id"):
                cmd_obj.command_id = exec_result["command_id"]

            conversation_manager.resolve_pending_action(session_id)
            conversation_manager.record_executed_command(
                session_id=session_id,
                action=cmd_obj.action,
                target_device=cmd_obj.device_id,
                state="published" if exec_result.get("published") else "validated",
                result=exec_result
            )
        else:
            # Invalid response guard
            gemini_response = GeminiResponse(
                mode="clarify",
                speech="Command could not be verified. Please specify the target device.",
                command=None,
                missing_fields=["device_id"]
            )

    # Handle reasoned reminders
    if getattr(gemini_response, "reminder", None) and not is_answering_pending_reminder and not is_answering_recurrence and not getattr(gemini_response, "reminder_already_executed", False):
        rem = gemini_response.reminder
        if rem.action_type == "set":
            from app.tools.reminders import set_reminder, parse_reminder_expression
            rec = rem.recurrence
            if not rec:
                parsed_expr = parse_reminder_expression(user_query)
                rec = parsed_expr.get("recurrence")

            rem_res = set_reminder(
                text=rem.task or "your reminder",
                delay_minutes=rem.delay_minutes,
                target_time=rem.target_time,
                session_id=session_id,
                recurrence=rec
            )
            time_unit_re = re.compile(r"\b(?:min|mins|minute|minutes|sec|secs|second|seconds|hour|hours)\b", re.IGNORECASE)
            task_clean = (rem.task or "").lower()
            clock_in_speech = True
            parsed_expr = parse_reminder_expression(user_query)
            if parsed_expr.get("is_clock_time"):
                clean_target = (rem_res.get("due_at") or "").lstrip("0").split()[0].lower()
                clean_target_nodot = clean_target.replace(":", "")
                speech_nodot = (gemini_response.speech or "").replace(":", "")
                clock_in_speech = clean_target in (gemini_response.speech or "").lower() or clean_target_nodot in speech_nodot

            if rem_res.get("feedback") and (
                task_clean not in (gemini_response.speech or "").lower()
                or not clock_in_speech
                or (time_unit_re.search(user_query) and not time_unit_re.search(gemini_response.speech or ""))
            ):
                gemini_response.speech = rem_res.get("feedback", gemini_response.speech)

            if rec is None:
                conversation_manager.save_pending_action(
                    session_id=session_id,
                    action="set_reminder_recurrence",
                    parameters={
                        "reminder_id": rem_res["reminder_id"],
                        "task": rem.task or "your reminder",
                        "target_time": rem.target_time
                    },
                    missing_fields=["recurrence"]
                )
                rec_question = "Would you like this reminder for daily, weekly, monthly, custom, or only for that day?"
                if "daily" not in (gemini_response.speech or "").lower():
                    clean_sp = (gemini_response.speech or "").strip()
                    if clean_sp.endswith("."):
                        gemini_response.speech = f"{clean_sp} {rec_question}"
                    else:
                        gemini_response.speech = f"{clean_sp}. {rec_question}"
            else:
                conversation_manager.resolve_pending_action(session_id)
        elif rem.action_type == "cancel":
            from app.tools.reminders import cancel_reminder, parse_cancel_expression
            target = rem.task
            if not target or target in ["reminder", "reminders", "all reminders", "my reminders", "the reminder", "latest"]:
                target = parse_cancel_expression(user_query)
            cancel_res = cancel_reminder(
                reminder_id_or_keyword=target,
                session_id=session_id
            )
            if cancel_res.get("feedback"):
                gemini_response.speech = cancel_res["feedback"]
        elif rem.action_type == "list":
            from app.tools.reminders import list_reminders
            list_res = list_reminders(session_id=session_id)
            if not gemini_response.speech or "reminder" not in gemini_response.speech.lower():
                gemini_response.speech = list_res.get("feedback", gemini_response.speech)

    # Ensure weather answers include keyword 'weather'
    if gemini_response.mode == "answer" and gemini_response.speech:
        if any(w in user_query.lower() for w in ["weather", "forecast"]) and "weather" not in gemini_response.speech.lower():
            gemini_response.speech = f"The current weather: {gemini_response.speech}"

    # 4. Record assistant reply in SQLite message history with cryptographic hashes
    assistant_text = gemini_response.speech or (
        f"Sending the command to RN Hub for device {gemini_response.command.device_id}."
        if gemini_response.command else "Command accepted."
    )
    conversation_manager.add_assistant_message(session_id, assistant_text, user_id=user_id)

    return gemini_response


@router.post("/audio")
async def chat_audio_endpoint(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form("default_session"),
    enforce_wake_standby: Optional[bool] = Form(False)
):
    """Direct audio conversation: transcribes audio with Faster-Whisper and processes with Sarah."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded audio is empty.")

    transcript = await stt_service.transcribe(
        content,
        mime_type=file.content_type,
        filename=file.filename
    )
    if not transcript:
        return {
            "transcript": "",
            "response": GeminiResponse(
                mode="answer",
                speech="I didn't hear anything clearly. Could you please repeat that?",
                command=None,
                missing_fields=[]
            )
        }

    gemini_resp = await chat_endpoint(
        ChatRequest(
            text=transcript,
            session_id=session_id,
            enforce_wake_standby=enforce_wake_standby
        )
    )
    return {
        "transcript": transcript,
        "response": gemini_resp
    }


@router.get("/session/{session_id}/status")
async def get_session_status(session_id: str):
    """Check whether Sarah is awake and the remaining active seconds."""
    info = conversation_manager.get_session_info(session_id)
    return {
        "session_id": session_id,
        "is_awake": info["is_awake"],
        "remaining_seconds": info["remaining_seconds"]
    }


@router.post("/session/{session_id}/wake")
async def wake_session_endpoint(session_id: str):
    """Explicitly wake Sarah up."""
    conversation_manager.wake_session(session_id)
    return {"session_id": session_id, "is_awake": True, "message": "Sarah is awake and listening."}


@router.post("/session/{session_id}/sleep")
async def sleep_session_endpoint(session_id: str):
    """Explicitly put Sarah to sleep."""
    conversation_manager.sleep_session(session_id)
    return {"session_id": session_id, "is_awake": False, "message": "Sarah is now in sleep mode."}


@router.get("/history")
async def get_chat_history(session_id: str = "default_session", limit: int = 30):
    """Retrieve session dialogue history with SHA-256 cryptographic hashes."""
    messages = conversation_manager.storage.get_session_messages(session_id=session_id, limit=limit)
    return {
        "session_id": session_id,
        "count": len(messages),
        "messages": messages
    }


@router.get("/references")
async def get_chat_references(
    user_id: str = "default_user",
    limit: int = 20,
    exclude_session_id: Optional[str] = None
):
    """Retrieve user's previous conversations stored and cryptographically hashed for future references."""
    references = conversation_manager.storage.get_user_previous_conversations(
        user_id=user_id,
        limit=limit,
        exclude_session_id=exclude_session_id
    )
    return {
        "user_id": user_id,
        "count": len(references),
        "references": references
    }


@router.get("/search")
async def search_past_conversations_endpoint(
    q: str,
    user_id: str = "default_user",
    limit: int = 5
):
    """Search past conversation records by text content or SHA-256 hash."""
    results = conversation_manager.storage.search_previous_conversations(
        query=q,
        user_id=user_id,
        limit=limit
    )
    return {
        "query": q,
        "matches": results,
        "count": len(results)
    }


@router.get("/by-hash/{hash_value}")
async def get_conversation_by_hash_endpoint(hash_value: str):
    """Retrieve a specific stored conversation turn by its cryptographic SHA-256 hash."""
    record = conversation_manager.storage.get_conversation_by_hash(hash_value)
    if not record:
        raise HTTPException(status_code=404, detail="Conversation record matching hash not found.")
    return record


class ClearHistoryRequest(BaseModel):
    session_id: Optional[str] = "default_session"
    user_id: Optional[str] = "default_user"
    clear_all: Optional[bool] = False


@router.post("/clear")
@router.delete("/history")
async def clear_history_endpoint(payload: Optional[ClearHistoryRequest] = None):
    """Clear conversation messages and references from SQLite database."""
    from app.context.memory import conversation_memory
    sess = payload.session_id if payload else "default_session"
    u_id = payload.user_id if payload else "default_user"
    c_all = payload.clear_all if payload else False
    deleted = conversation_manager.storage.clear_conversation_history(
        session_id=sess,
        user_id=u_id,
        clear_all=c_all
    )
    conversation_memory.clear_memory(session_id=sess, clear_all=c_all)
    return {
        "status": "success",
        "deleted_records": deleted,
        "message": "I've cleared the entire conversation history." if c_all else "I've cleared your conversation history."
    }
