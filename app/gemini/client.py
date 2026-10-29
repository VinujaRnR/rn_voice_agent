import os
import json
import logging
import asyncio
from typing import Optional, List, Dict, Any
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from pydantic import ValidationError

from app.config import settings
from app.gemini.prompts import SYSTEM_INSTRUCTION, get_system_instruction
from app.gemini.schemas import GeminiResponse, DeviceCommand

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model or settings.gemini_model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self._client: Optional[Any] = None

    @property
    def client(self) -> Optional[Any]:
        import asyncio
        try:
            curr_loop = asyncio.get_running_loop()
        except RuntimeError:
            curr_loop = None

        if self._client is None or getattr(self, "_bound_loop", None) != curr_loop:
            self._client = genai.Client(api_key=self.api_key)
            self._bound_loop = curr_loop
        return self._client

    async def generate_response(
        self,
        prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None
    ) -> GeminiResponse:
        """Generate structured response using GeminiResponse schema with cross-field validation."""
        # Check for unconfigured API key
        if not self.api_key or self.api_key.startswith("YOUR_API_KEY"):
            return GeminiResponse(
                mode="answer",
                speech="Gemini API key is not configured. Please add your key to .env.",
                command=None,
                missing_fields=[]
            )

        try:
            # Build conversation context with live time and reminder schedule
            from datetime import datetime
            now_dt = datetime.now()
            time_str = now_dt.strftime("%I:%M %p, %A, %B %d, %Y")

            full_prompt_lines = [f"Context: Current Local Time is {time_str}."]

            try:
                from app.tools.reminders import list_reminders
                active_rem_data = list_reminders(session_id=session_id)
                if active_rem_data.get("reminders"):
                    rem_descs = [f"- '{r['text']}' at {r['due_at']} (id: {r['id']})" for r in active_rem_data["reminders"]]
                    full_prompt_lines.append("Active Reminders in Schedule for this session:\n" + "\n".join(rem_descs))
                else:
                    full_prompt_lines.append("Active Reminders in Schedule for this session: None")
            except Exception:
                pass

            # Context Reasoning: Inject pending clarification state if active
            if session_id:
                try:
                    from app.conversation.manager import conversation_manager
                    pending = conversation_manager.get_pending_action(session_id)
                    if pending and pending.get("missing_fields"):
                        full_prompt_lines.append(
                            f"\nPending Clarification Context: The user previously requested action '{pending.get('action')}' "
                            f"with state '{pending.get('state')}' but device was ambiguous. "
                            f"Missing fields: {pending.get('missing_fields')}. "
                            "If user input clarifies the device or refers to it, resolve and execute immediately."
                        )
                except Exception:
                    pass

            if conversation_history:
                full_prompt_lines.append("\nPrevious Conversation:")
                for msg in conversation_history[-6:]:
                    role = "User" if msg.get("role") == "user" else "Assistant"
                    full_prompt_lines.append(f"{role}: {msg.get('content', '')}")
                full_prompt_lines.append("\nCurrent User Input:")

            full_prompt_lines.append(prompt)
            contents = "\n".join(full_prompt_lines)

            # Configure thinking config if supported by model/SDK
            thinking_config = None
            budget = getattr(settings, "gemini_thinking_budget", 1024)
            if budget > 0 and types and hasattr(types, "ThinkingConfig"):
                try:
                    thinking_config = types.ThinkingConfig(thinking_budget=budget)
                except Exception as te:
                    logger.debug(f"ThinkingConfig init: {te}")

            # Configure structured JSON output with GeminiResponse and thinking configuration
            config_kwargs: Dict[str, Any] = {
                "system_instruction": get_system_instruction(),
                "response_mime_type": "application/json",
                "response_schema": GeminiResponse,
                "temperature": getattr(settings, "gemini_temperature", 0.2),
            }
            if thinking_config is not None:
                config_kwargs["thinking_config"] = thinking_config

            config = types.GenerateContentConfig(**config_kwargs)

            for attempt in range(2):
                try:
                    response = await self.client.aio.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config,
                    )
                    break
                except Exception as ex:
                    ex_msg = str(ex)
                    # If model does not support thinking_config, fall back gracefully
                    if "thinking" in ex_msg.lower() and "thinking_config" in config_kwargs:
                        logger.warning("Model rejected thinking_config, retrying without thinking budget...")
                        config_kwargs.pop("thinking_config", None)
                        config = types.GenerateContentConfig(**config_kwargs)
                        continue
                    if ("503" in ex_msg or "UNAVAILABLE" in ex_msg or "high demand" in ex_msg) and attempt == 0:
                        logger.warning("Gemini 503 spike, retrying after 1s...")
                        await asyncio.sleep(1.0)
                        continue
                    raise

            if not response.text:
                return GeminiResponse(
                    mode="answer",
                    speech="No response received from Gemini.",
                    command=None,
                    missing_fields=[]
                )

            # Parse and validate with Pydantic (including cross-field validation)
            parsed_data = json.loads(response.text)
            gemini_response = GeminiResponse.model_validate(parsed_data)
            if gemini_response.reasoning:
                logger.info(f"[Sarah Reasoning]: {gemini_response.reasoning}")
            return gemini_response

        except ValidationError as ve:
            logger.error(f"Gemini response failed cross-field validation: {ve}")
            # Invalid response is caught here and blocked from reaching executor
            return GeminiResponse(
                mode="answer",
                speech="The generated command failed safety validation and was rejected.",
                command=None,
                missing_fields=[]
            )

        except Exception as e:
            err_msg = str(e)
            logger.error(f"Gemini API request failed: {err_msg}")
            if "API key not valid" in err_msg or "API_KEY_INVALID" in err_msg:
                return GeminiResponse(
                    mode="answer",
                    speech="The provided Gemini API key in .env is invalid. Please check your Google AI Studio key.",
                    command=None,
                    missing_fields=[]
                )
            return None
