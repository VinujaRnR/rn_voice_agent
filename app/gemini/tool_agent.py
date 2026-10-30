"""Gemini 3.5 Flash-Lite Tool Orchestrator and Agent."""
import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types

from app.config import settings
from app.gemini.tools import TOOLS
from app.gemini.schemas import GeminiResponse, DeviceCommand
from app.tools.time_weather import get_current_time, get_weather
from app.tools.web_search import search_web
from app.tools.places import search_places, extract_location, extract_cuisine
from app.tools.device_status import list_devices, get_device_status
from app.tools.device_control import control_device, schedule_device_action
from app.tools.reminders import set_reminder, list_reminders, cancel_reminder, parse_reminder_expression, parse_cancel_expression
from app.security.command_validator import command_safety_validator
from app.context.builder import context_builder
from app.context.memory import conversation_memory
from app.stt.accent_normalizer import normalize_accent_transcript

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"


def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a validated Python tool handler."""
    args = arguments or {}

    try:
        if name == "get_current_time":
            tz = args.get("timezone", "Asia/Colombo")
            return get_current_time(timezone=tz)

        elif name == "get_weather":
            city = args.get("city", "Colombo")
            days = args.get("forecast_days", 1)
            return get_weather(city=city, forecast_days=days)

        elif name == "search_web":
            query = args.get("query", "")
            return search_web(query=query)

        elif name == "search_places":
            query = args.get("query", "restaurants")
            loc = args.get("location", "Colombo")
            return search_places(query=query, location=loc)

        elif name == "list_devices":
            return list_devices()

        elif name == "get_device_status":
            dev_id = args.get("device_id", "")
            return get_device_status(device_id=dev_id)

        elif name == "control_device":
            dev_id = args.get("device_id", "")
            action = args.get("action", "")
            params = args.get("parameters", {})
            valid, msg = command_safety_validator.validate_command(dev_id, action, params)
            if not valid:
                return {"error": msg, "status": "safety_violation"}
            return control_device(device_id=dev_id, action=action, parameters=params)

        elif name == "schedule_device_action":
            dev_id = args.get("device_id", "")
            action = args.get("action", "")
            delay = args.get("delay_minutes", 15)
            params = args.get("parameters", {})
            return schedule_device_action(device_id=dev_id, action=action, delay_minutes=delay, parameters=params)

        elif name == "set_reminder":
            text = args.get("text", "")
            delay_secs = args.get("delay_seconds")
            delay_mins = args.get("delay_minutes")
            sess = args.get("session_id", "default_session")
            return set_reminder(text=text, delay_seconds=delay_secs, delay_minutes=delay_mins, session_id=sess)

        elif name == "list_reminders":
            sess = args.get("session_id")
            return list_reminders(session_id=sess)

        elif name == "cancel_reminder":
            target = args.get("reminder_id", "all")
            sess = args.get("session_id")
            return cancel_reminder(reminder_id_or_keyword=target, session_id=sess)

        elif name == "search_past_conversations":
            q = args.get("query", "")
            user_id = args.get("user_id", "default_user")
            results = conversation_memory.search_past_conversations(query=q, user_id=user_id)
            return {
                "status": "success",
                "query": q,
                "count": len(results),
                "matches": [
                    {
                        "role": m["role"],
                        "content": m["content"],
                        "content_hash": m.get("content_hash"),
                        "turn_hash": m.get("turn_hash"),
                        "timestamp": m.get("timestamp")
                    }
                    for m in results
                ]
            }

        elif name == "clarify_weather_context":
            return {
                "status": "clarification_needed",
                "speech": "Where are you heading, or would you like the weather forecast for your current location in Colombo?"
            }

        return {"error": f"Unknown or unauthorized tool: '{name}'"}

    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}")
        return {"error": f"Tool execution failed: {str(e)}"}


class ToolAgent:
    """Orchestrates Gemini 3.5 Flash-Lite, trusted tool dispatch, and dynamic context."""

    def __init__(self):
        self.model_name = settings.gemini_model
        if "3.5" in self.model_name or "flash" in self.model_name:
            pass
        self._load_system_prompt()
        self._client = None
        self._bound_loop = None

    def _load_system_prompt(self):
        if SYSTEM_PROMPT_PATH.exists():
            self.system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        else:
            self.system_prompt = "You are RN Assistant, the intelligent voice assistant developed by RN Robots."

    @property
    def client(self) -> Optional[genai.Client]:
        import asyncio
        try:
            curr_loop = asyncio.get_running_loop()
        except RuntimeError:
            curr_loop = None

        if self._client is None or getattr(self, "_bound_loop", None) != curr_loop:
            api_key = settings.gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
            if api_key:
                try:
                    self._client = genai.Client(api_key=api_key)
                except Exception as e:
                    logger.warning(f"Failed to initialize Gemini Client: {e}")
                    self._client = None
            else:
                self._client = None
            self._bound_loop = curr_loop
        return self._client

    def _detect_tools_heuristically(self, query: str, session_id: Optional[str] = None) -> List[tuple[str, Dict[str, Any]]]:
        """Detect which tools are required based on user intent."""
        normalized = normalize_accent_transcript(query)
        q = normalized.lower()
        tools_to_run = []

        # Weather intent
        if any(w in q for w in ["weather", "temperature", "forecast", "rain", "humid", "raining"]):
            city = None
            for candidate in ["tokyo", "kandy", "galle", "london", "paris", "new york", "dubai", "colombo"]:
                if candidate in q:
                    city = candidate.title()
                    break

            # Resolve references to previous location ("there", "that place", or follow-up question)
            if not city and session_id:
                has_loc_ref = bool(re.search(r"\b(?:there|that city|that place|same place|in it)\b", q)) or (
                    any(w in q for w in ["rain", "raining", "forecast", "tomorrow", "temperature", "cold", "hot"])
                )
                ref_city = conversation_memory.get_referenced_entity(session_id, "location")
                if ref_city and has_loc_ref:
                    city = ref_city
                else:
                    recent_msgs = conversation_memory.get_recent_messages(session_id, limit=4)
                    for m in reversed(recent_msgs):
                        m_text = m.get("content", "").lower()
                        for candidate in ["tokyo", "kandy", "galle", "london", "paris", "new york", "dubai", "colombo"]:
                            if candidate in m_text:
                                city = candidate.title()
                                break
                        if city:
                            break

            if not city and (bool(re.search(r"\b(?:here|local)\b", q)) or any(k in q for k in ["current location", "my location"])):
                city = "Colombo"

            if city:
                if session_id:
                    conversation_memory.set_referenced_entity(session_id, "location", city)
                tools_to_run.append(("get_weather", {"city": city, "forecast_days": 2 if "tomorrow" in q else 1}))
            else:
                tools_to_run.append(("clarify_weather_context", {}))

        # Check if user query is a follow-up answer providing location to Sarah's weather clarification
        elif session_id:
            recent_msgs = conversation_memory.get_recent_messages(session_id, limit=3)
            is_weather_followup = any(
                "weather" in m.get("content", "").lower() and any(k in m.get("content", "").lower() for k in ["where", "heading", "going", "destination", "location"])
                for m in recent_msgs
            )
            if is_weather_followup:
                found_city = None
                for candidate in ["tokyo", "kandy", "galle", "london", "paris", "new york", "dubai", "colombo"]:
                    if candidate in q:
                        found_city = candidate.title()
                        break
                if not found_city and (bool(re.search(r"\b(?:here|current)\b", q)) or "colombo" in q):
                    found_city = "Colombo"
                if found_city:
                    conversation_memory.set_referenced_entity(session_id, "location", found_city)
                    tools_to_run.append(("get_weather", {"city": found_city, "forecast_days": 1}))

        # Time intent
        if any(w in q for w in ["what time", "current time", "time in", "what's the time", "what date", "date is it"]):
            tz = "Asia/Colombo"
            found_tz_city = None
            for city_key, tz_val in [("tokyo", "Asia/Tokyo"), ("london", "Europe/London"), ("new york", "America/New_York"), ("colombo", "Asia/Colombo"), ("paris", "Europe/Paris")]:
                if city_key in q:
                    tz = tz_val
                    found_tz_city = city_key
                    break
            if not found_tz_city and any(ref in q for ref in ["there", "that city", "that place"]) and session_id:
                ref_city = (conversation_memory.get_referenced_entity(session_id, "location") or "").lower()
                for city_key, tz_val in [("tokyo", "Asia/Tokyo"), ("london", "Europe/London"), ("new york", "America/New_York"), ("colombo", "Asia/Colombo"), ("paris", "Europe/Paris")]:
                    if city_key in ref_city:
                        tz = tz_val
                        break
            tools_to_run.append(("get_current_time", {"timezone": tz}))

        # Places / Restaurants intent
        cuisine = extract_cuisine(q)
        place_kws = ["restaurant", "restaurants", "dinner", "lunch", "café", "cafe", "food", "dining", "pizzeria"]
        has_place_kw = any(re.search(r"\b" + re.escape(w) + r"\b", q) for w in place_kws) or bool(re.search(r"\b(?:places?\s+to\s+eat|where\s+to\s+eat|\beat\b)\b", q))
        if has_place_kw or (cuisine and bool(re.search(r"\b(?:in|around|near|find|where|best|good)\b", q))):
            loc = extract_location(normalized, default="Colombo")
            if session_id and loc:
                conversation_memory.set_referenced_entity(session_id, "location", loc)
            query_term = cuisine or ("dinner" if "dinner" in q else ("seafood" if "seafood" in q else "restaurants"))
            tools_to_run.append(("search_places", {"query": query_term, "location": loc}))

        # Web search intent
        if any(w in q for w in ["search the internet", "search web", "latest research", "robotics research", "google search", "news on"]):
            clean_q = q.replace("search the internet for", "").replace("search the web for", "").replace("search for", "").strip()
            tools_to_run.append(("search_web", {"query": clean_q or q}))

        # Reminder intents
        is_cancel_rem = bool(re.search(r"\b(?:cancel|clear|remove|delete)\b.*?\breminders?\b", q)) or q.strip().startswith(("cancel reminder", "clear reminder", "cancel reminders", "clear reminders", "cancel all reminders", "cancel"))
        is_list_rem = bool(re.search(r"\b(?:what are my reminders|list reminders|list my reminders|show reminders|show my reminders|active reminders|what reminders|reminders list)\b", q))
        is_set_rem = bool(re.search(r"\b(?:remind me|set a reminder|schedule a reminder|remind us|create a reminder)\b", q))

        if is_cancel_rem and not any(w in q for w in ["what", "how", "list", "show"]):
            target_kw = parse_cancel_expression(normalized)
            tools_to_run.append(("cancel_reminder", {"reminder_id": target_kw}))
        elif is_list_rem:
            tools_to_run.append(("list_reminders", {}))
        elif is_set_rem:
            parsed = parse_reminder_expression(normalized)
            tools_to_run.append(("set_reminder", {
                "text": parsed["text"],
                "delay_seconds": parsed["delay_seconds"]
            }))

        # Past conversation recall intent
        is_recall = bool(re.search(
            r"\b(?:what did (?:we|i|you) (?:talk|say|ask|discuss|mention)|do you (?:remember|recall)|earlier conversation|previous conversation|past conversation|repeat what you (?:just )?said|what was (?:my|that) (?:last |previous )?(?:question|topic|item|request)|what did i just (?:say|ask))\b",
            q
        ))
        if is_recall:
            clean_term = re.sub(
                r"\b(?:what did (?:we|i|you) (?:talk|say|ask|discuss|mention)|do you (?:remember|recall)|about|earlier|previous|conversation|in the past|repeat what you (?:just )?said|what was (?:my|that) (?:last |previous )?(?:question|topic|item|request)|what did i just (?:say|ask)|please|can you|could you)\b",
                "",
                q
            ).strip()
            tools_to_run.append(("search_past_conversations", {"query": clean_term or ""}))

        # Device status intent (e.g., "Are the farm lights on?", "whether the testing farm lights are on")
        is_science_or_knowledge = any(k in q for k in ["speed of light", "why is", "how does", "what is light", "explain", "meaning of", "tell me about"])
        if not is_science_or_knowledge:
            is_status_ask = (
                any(p in q for p in ["are on", "is on", "are off", "is off", "status of", "check status"]) or
                (any(p in q for p in ["are the", "is the", "whether the", "check if the"]) and any(s in q for s in ["on", "off", "working", "status", "state"]))
            )
            if is_status_ask and any(d in q for d in ["light", "lights", "farm", "thermostat", "robot"]):
                dev_id = "98a316e6b658" if ("farm" in q) else ("room_lights" if "room" in q else "kitchen_lights")
                tools_to_run.append(("get_device_status", {"device_id": dev_id}))

        # Device control intent (e.g. "Turn on the testing farm lights")
        elif any(act in q for act in ["turn on", "turn off", "switch on", "switch off", "power on", "power off"]):
            action = "turn_on" if any(x in q for x in ["turn on", "switch on", "power on"]) else "turn_off"
            dev_id = "98a316e6b658" if "farm" in q else ("room_lights" if "room" in q else ("kitchen_lights" if "kitchen" in q else "desk_lamp"))
            if any(t in q for t in ["after", "in 10 minutes", "in 20 minutes", "in 30 minutes", "later"]):
                tools_to_run.append(("schedule_device_action", {"device_id": dev_id, "action": action, "delay_minutes": 20}))
            else:
                tools_to_run.append(("control_device", {"device_id": dev_id, "action": action, "parameters": {"state": "on" if action == "turn_on" else "off"}}))

        return tools_to_run

    def needs_tools(self, query: str, session_id: Optional[str] = None) -> bool:
        """Check if query requires external tools (weather, time, web search, places, IoT devices)."""
        return len(self._detect_tools_heuristically(query, session_id=session_id)) > 0

    async def run(
        self,
        query: str,
        session_id: str,
        dynamic_context: Optional[Dict[str, Any]] = None
    ) -> GeminiResponse:
        """Run the full Gemini + tool execution pipeline."""
        ctx = dynamic_context or context_builder.build_context(session_id)

        # 1. Identify which tools to execute
        tools_to_call = self._detect_tools_heuristically(query, session_id=session_id)
        tool_results: Dict[str, Any] = {}
        device_command_obj: Optional[DeviceCommand] = None

        for tool_name, tool_args in tools_to_call:
            if "session_id" not in tool_args and session_id:
                tool_args["session_id"] = session_id
            res = execute_tool(tool_name, tool_args)
            tool_results[tool_name] = res

            # If tool was device control, extract the proposed command
            if tool_name == "control_device" and res.get("status") == "success":
                cmd_data = res.get("command", {})
                device_command_obj = DeviceCommand(
                    device_id=cmd_data.get("device_id", "98a316e6b658"),
                    action=cmd_data.get("action", "set_power"),
                    parameters=cmd_data.get("parameters", {"state": "on"})
                )

        # 2. If Gemini client is live and configured, generate model synthesis with tool evidence
        if self.client and settings.gemini_api_key:
            try:
                recent_msgs = conversation_memory.get_recent_messages(session_id, limit=12) if session_id else []
                dialogue_lines = []
                for msg in recent_msgs:
                    r_label = "User" if msg.get("role") == "user" else "Sarah"
                    dialogue_lines.append(f"{r_label}: {msg.get('content', '')}")
                dialogue_text = "\n".join(dialogue_lines) if dialogue_lines else "None"

                evidence_text = (
                    f"User Query: {query}\n"
                    f"Recent Dialogue History:\n{dialogue_text}\n"
                    f"Dynamic Context: {json.dumps(ctx)}\n"
                    f"Verified Tool Results: {json.dumps(tool_results)}\n"
                    "Instructions: Synthesize the verified tool evidence and recent dialogue history into a clear, accurate, natural voice response. "
                    "If the user asks follow-up questions, refers to pronouns ('there', 'that', 'it', 'them'), or references recent conversations, incorporate the recent dialogue history accurately."
                )

                thinking_config = None
                budget = getattr(settings, "gemini_thinking_budget", 1024)
                if budget > 0 and types and hasattr(types, "ThinkingConfig"):
                    try:
                        thinking_config = types.ThinkingConfig(thinking_budget=budget)
                    except Exception:
                        pass

                config_kwargs = {
                    "system_instruction": self.system_prompt,
                    "temperature": getattr(settings, "gemini_temperature", 0.2),
                }
                if thinking_config is not None:
                    config_kwargs["thinking_config"] = thinking_config

                try:
                    resp = await self.client.aio.models.generate_content(
                        model=self.model_name,
                        contents=evidence_text,
                        config=types.GenerateContentConfig(**config_kwargs)
                    )
                except Exception as mex:
                    if "thinking" in str(mex).lower() and "thinking_config" in config_kwargs:
                        config_kwargs.pop("thinking_config", None)
                        resp = await self.client.aio.models.generate_content(
                            model=self.model_name,
                            contents=evidence_text,
                            config=types.GenerateContentConfig(**config_kwargs)
                        )
                    else:
                        raise

                if resp and resp.text:
                    spoken = resp.text.strip()
                    if "clarify_weather_context" in tool_results and "weather" not in spoken.lower():
                        spoken = f"{spoken} Would you like the weather forecast for Colombo?"
                    if "get_weather" in tool_results and "weather" not in spoken.lower():
                        spoken = f"The current weather: {spoken}"
                    if "search_web" in tool_results and "top web search results" not in spoken.lower():
                        spoken = f"Top web search results: {spoken}"
                    if "set_reminder" in tool_results:
                        rem_fb = tool_results["set_reminder"].get("feedback")
                        time_unit_re = re.compile(r"\b(?:min|mins|minute|minutes|sec|secs|second|seconds|hour|hours)\b", re.IGNORECASE)
                        if rem_fb and time_unit_re.search(query) and not time_unit_re.search(spoken):
                            spoken = rem_fb
                    mode_val = "device_command" if device_command_obj else "answer"
                    reasoning_trace = f"Synthesized evidence from executed tools: {list(tool_results.keys())}."
                    return GeminiResponse(
                        reasoning=reasoning_trace,
                        mode=mode_val,
                        speech=spoken,
                        command=device_command_obj,
                        missing_fields=[]
                    )
            except Exception as e:
                logger.warning(f"Gemini live inference fallback ({e}). Using deterministic tool synthesis.")

        # 3. Deterministic tool evidence synthesis
        spoken_parts = []

        if "clarify_weather_context" in tool_results:
            spoken_parts.append("Where are you heading, or would you like the weather forecast for your current location in Colombo?")

        if "get_weather" in tool_results:
            w = tool_results["get_weather"]
            spoken_parts.append(f"In {w.get('city')}, the current weather is {w.get('temperature')} with {w.get('condition').lower()}.")

        if "get_current_time" in tool_results:
            t = tool_results["get_current_time"]
            city_label = t.get("timezone", "").split("/")[-1].replace("_", " ")
            spoken_parts.append(f"The time in {city_label} is {t.get('time')}.")

        if "search_places" in tool_results:
            p = tool_results["search_places"]
            places = p.get("places", [])
            if places:
                top_p = places[0]
                spoken_parts.append(f"A great restaurant option in {p.get('location')} is {top_p['name']} ({top_p.get('category')}, rated {top_p.get('rating')} stars).")

        if "get_device_status" in tool_results:
            st = tool_results["get_device_status"]
            status_text = "turned on" if st.get("power_state") == "on" else "turned off"
            spoken_parts.append(f"The {st.get('name', 'device')} is currently {status_text}.")

        if "search_web" in tool_results:
            sw = tool_results["search_web"]
            results = sw.get("results", [])
            if results:
                spoken_parts.append(f"According to recent research on {sw.get('query')}: {results[0].get('snippet')[:140]}...")

        if "schedule_device_action" in tool_results:
            sch = tool_results["schedule_device_action"]
            spoken_parts.append(sch.get("feedback"))

        if "control_device" in tool_results:
            cd = tool_results["control_device"]
            spoken_parts.append(cd.get("feedback", "Sending command to RN Hub."))

        if "set_reminder" in tool_results:
            rem = tool_results["set_reminder"]
            spoken_parts.append(rem.get("feedback", "Reminder scheduled."))

        if "list_reminders" in tool_results:
            lrem = tool_results["list_reminders"]
            spoken_parts.append(lrem.get("feedback", "Here are your active reminders."))

        if "cancel_reminder" in tool_results:
            crem = tool_results["cancel_reminder"]
            spoken_parts.append(crem.get("feedback", "Reminder cancelled."))

        if "search_past_conversations" in tool_results:
            sp = tool_results["search_past_conversations"]
            matches = sp.get("matches", [])
            if matches:
                recent_user = [m['content'] for m in matches if m.get('role') == 'user']
                if recent_user:
                    spoken_parts.append(f"Earlier in our conversation, you mentioned: '{recent_user[0]}'.")
                else:
                    spoken_parts.append(f"Earlier, we discussed: '{matches[0]['content']}'.")
            else:
                spoken_parts.append("I checked our previous conversation records, but couldn't find matching notes.")

        if not spoken_parts:
            spoken_parts.append(f"I received your request: '{query}'. How can I assist you further?")

        final_speech = " ".join(spoken_parts)
        mode = "device_command" if device_command_obj else "answer"

        return GeminiResponse(
            mode=mode,
            speech=final_speech,
            command=device_command_obj,
            missing_fields=[]
        )


tool_agent = ToolAgent()
