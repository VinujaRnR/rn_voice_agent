"""Reminder and scheduling tool for Sarah."""
import re
import uuid
import time
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from app.conversation.storage import ConversationStorage

logger = logging.getLogger(__name__)
storage = ConversationStorage()

# In-memory store for recently fired reminder alerts (for UI or audio announcement)
fired_reminders_log: List[Dict[str, Any]] = []


def convert_first_person_to_second_person(text: str) -> str:
    """Convert first-person pronouns ('my', 'me', 'myself', 'mine', 'our', etc.) to second-person ('your', 'you', etc.) for natural voice reminders."""
    if not text:
        return ""

    replacements = [
        (r"\bmyself\b", "yourself"),
        (r"\bourselves\b", "yourselves"),
        (r"\bmine\b", "yours"),
        (r"\bours\b", "yours"),
        (r"\bmy\b", "your"),
        (r"\bour\b", "your"),
        (r"\bi\s*am\b", "you are"),
        (r"\bi'm\b", "you're"),
        (r"\bi've\b", "you've"),
        (r"\bi'll\b", "you'll"),
        (r"\bi'd\b", "you'd"),
        (r"\bi\b", "you"),
        (r"\bme\b", "you"),
    ]

    res = text
    for pattern, rep in replacements:
        def _rep(match, repl=rep):
            m = match.group(0)
            if m.isupper():
                return repl.upper()
            elif m[0].isupper():
                return repl.capitalize()
            return repl.lower()

        res = re.sub(pattern, _rep, res, flags=re.IGNORECASE)

    return res


INCOMPLETE_REMINDER_VERBS = {
    "take", "get", "buy", "call", "check", "do", "bring", "pick", "send", "turn",
    "make", "put", "give", "tell", "pay", "order", "eat", "drink", "see", "watch",
    "read", "write", "find", "clean", "fix", "water", "prepare", "finish", "start",
    "stop", "inspect", "feed", "wash", "remind", "look", "listen", "switch", "turn off",
    "turn on", "switch off", "switch on", "pick up", "look for", "listen to", "check on"
}

PLACEHOLDER_TASKS = {
    "", "your scheduled reminder", "a reminder", "reminder", "something", "it", "this", "that"
}


def is_incomplete_reminder_task(task_text: str, query: str) -> tuple[bool, Optional[str]]:
    """Determine if a reminder task description is incomplete or lacking context (e.g. 'take', 'call', 'buy').

    Returns (is_incomplete, identified_verb).
    """
    if not task_text:
        return True, None

    clean_task = task_text.strip().lower()
    if clean_task.startswith("to "):
        clean_task = clean_task[3:].strip()

    if clean_task in PLACEHOLDER_TASKS:
        return True, None

    if clean_task in INCOMPLETE_REMINDER_VERBS:
        return True, clean_task

    words = clean_task.split()
    if len(words) == 1 and words[0] in INCOMPLETE_REMINDER_VERBS:
        return True, words[0]

    dangling_particles = (" to", " for", " about", " with", " on", " of", " at", " in", " up", " off", " from")
    if clean_task.endswith(dangling_particles):
        return True, words[0] if words else None

    clean_query = query.strip().lower().rstrip(".?!")
    end_match = re.search(r"\b(?:remind\s+(?:me|us)?\s*(?:to|about|for)?|set\s+(?:a\s+)?reminder\s*(?:to|for|about)?)\s*(\w+)?$", clean_query)
    if end_match:
        trailing = (end_match.group(1) or "").strip()
        if not trailing or trailing in INCOMPLETE_REMINDER_VERBS:
            return True, trailing or (words[0] if words else None)

    return False, None


def generate_reminder_clarification_question(
    verb: Optional[str] = None,
    partial_task: Optional[str] = None,
    time_label: Optional[str] = None
) -> str:
    """Generate a natural clarifying question asking for the missing reminder context."""
    v = (verb or partial_task or "").lower().strip()
    time_suffix = f" {time_label}" if time_label else ""
    when_suffix = "?" if time_label else ", and when would you like the reminder?"
    if v == "take":
        return f"What would you like me to remind you to take{time_suffix}{when_suffix}"
    elif v in ["call", "phone", "contact"]:
        return f"Who would you like me to remind you to call{time_suffix}{when_suffix}"
    elif v in ["buy", "get", "purchase", "pick up", "order"]:
        return f"What would you like me to remind you to {v}{time_suffix}{when_suffix}"
    elif v in ["turn off", "turn on", "switch off", "switch on"]:
        return f"Which device or lights should I remind you to {v}{time_suffix}{when_suffix}"
    elif v and v not in PLACEHOLDER_TASKS:
        return f"What would you like me to remind you to {v}{time_suffix}{when_suffix}"
    return "What would you like me to remind you about, and when should I set it for?"


def parse_target_clock_time(time_str: str, now: Optional[datetime] = None) -> int:
    """Parse clock time string like '4:30 p.m.', '4:30pm', '11.50 am', '16:30', '5 pm', '3:00', '3 o'clock' and return delay in seconds."""
    now = now or datetime.now()
    from app.commands.device_registry import normalize_spoken_numbers
    clean = normalize_spoken_numbers(time_str.lower().replace("a.m.", "am").replace("p.m.", "pm").strip())
    clean = re.sub(r"\b(\d{1,2})\s*(?:o['’]?\s*clock|oclock)\b", r"\1:00", clean)
    clean = re.sub(r"\b(\d{1,2}(?::\d{2})?)\s*(?:in the afternoon|in the evening|at night|tonight)\b", r"\1 pm", clean)
    clean = re.sub(r"\b(\d{1,2}(?::\d{2})?)\s*(?:in the morning)\b", r"\1 am", clean)

    m = re.search(r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?", clean)
    if not m:
        return 600

    raw_hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = m.group(3)

    if meridiem == "pm":
        hour = 12 if raw_hour == 12 else (raw_hour + 12 if raw_hour < 12 else raw_hour)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        diff = (target - now).total_seconds()
        if diff < -120:
            target += timedelta(days=1)
            diff = (target - now).total_seconds()
        if -120 <= diff <= 0:
            return 10
        return max(5, int(diff))

    elif meridiem == "am":
        hour = 0 if raw_hour == 12 else raw_hour
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        diff = (target - now).total_seconds()
        if diff < -120:
            target += timedelta(days=1)
            diff = (target - now).total_seconds()
        if -120 <= diff <= 0:
            return 10
        return max(5, int(diff))

    elif raw_hour > 12:
        hour = raw_hour
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        diff = (target - now).total_seconds()
        if diff < -120:
            target += timedelta(days=1)
            diff = (target - now).total_seconds()
        if -120 <= diff <= 0:
            return 10
        return max(5, int(diff))

    else:
        # 12-hour format without meridiem (e.g. "3 o'clock", "3:00", "8")
        am_hour = 0 if raw_hour == 12 else raw_hour
        pm_hour = 12 if raw_hour == 12 else raw_hour + 12

        # 1-6 o'clock defaults to afternoon/evening (PM) unless specified
        if 1 <= raw_hour <= 6:
            hours_to_check = [pm_hour]
        elif 7 <= raw_hour <= 11:
            hours_to_check = [am_hour, pm_hour]
        else:
            # 12 o'clock defaults to noon (12:00 PM)
            hours_to_check = [12]

        candidates = []
        for h in hours_to_check:
            for day_offset in [0, 1]:
                cand = (now + timedelta(days=day_offset)).replace(hour=h, minute=minute, second=0, microsecond=0)
                diff = (cand - now).total_seconds()
                if diff >= -120:
                    candidates.append((diff, cand))

        if not candidates:
            return 600

        candidates.sort(key=lambda x: x[0])
        chosen_diff, _ = candidates[0]
        if -120 <= chosen_diff <= 0:
            return 10
        return max(5, int(chosen_diff))


def parse_reminder_expression(query: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Parse reminder intent, task text, and duration/time from spoken or typed query."""
    now = now or datetime.now()
    q = query.strip()
    clean = q.lower()

    # 1. Normalize speech typos, number words, and clock representations
    clean = re.sub(r"\bturn of\b", "turn off", clean)
    from app.commands.device_registry import normalize_spoken_numbers
    clean = normalize_spoken_numbers(clean)

    # Convert o'clock expressions (e.g. "3 o'clock" -> "3:00", "3 oclock" -> "3:00", "3 o clock" -> "3:00")
    clean = re.sub(r"\b(\d{1,2})\s*(?:o['’]?\s*clock|oclock)\b", r"\1:00", clean)

    # Convert time of day qualifiers
    clean = re.sub(r"\b(\d{1,2}(?::\d{2})?)\s*(?:in the afternoon|in the evening|at night|tonight)\b", r"\1 pm", clean)
    clean = re.sub(r"\b(\d{1,2}(?::\d{2})?)\s*(?:in the morning)\b", r"\1 am", clean)

    # Convert standalone "at <hour>" or "by <hour>"
    clean = re.sub(r"\b(?:at|by)\s+(\d{1,2})\b(?!\s*(?:[:.]|seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?|am|pm|a\.m\.|p\.m\.))", r"at \1:00", clean)

    # Convert dot time representation (e.g. "11.50 am" -> "11:50 am", "11.50" -> "11:50")
    clean = re.sub(r"\b(\d{1,2})\.(\d{2})\s*(am|pm|a\.m\.|p\.m\.)", r"\1:\2 \3", clean)
    clean = re.sub(r"\b(\d{1,2})\.(\d{2})\b", r"\1:\2", clean)

    delay_seconds = 600
    detected_time_str = "10 minutes"
    is_clock_time = False

    # 2. Check for clock time like "in 11.50 am", "at 4:30 pm", "for 11:50 am", "by 5 pm", "in 3:00", "at 3:00"
    clock_m = re.search(r"\b(?:at|in|for|by|on)?\s*(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.))\b", clean, re.IGNORECASE)
    if not clock_m:
        clock_m = re.search(r"\b(?:at|in|for|by|on)?\s*(\d{1,2}[:.]\d{2}\s*(?:am|pm|a\.m\.|p\.m\.)?)\b", clean, re.IGNORECASE)

    if clock_m:
        time_token = clock_m.group(1)
        delay_seconds = parse_target_clock_time(time_token, now)
        is_clock_time = True
        target_dt = now + timedelta(seconds=delay_seconds)
        time_fmt = target_dt.strftime("%I:%M %p").lstrip("0")
        detected_time_str = f"at {time_fmt}"
    else:
        # Check relative duration like "in 10 minutes", "in 5 mins", "in 30 seconds", "in 1 hour"
        time_regex = re.search(
            r"\bin\s+(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b",
            clean
        )
        if time_regex:
            qty = float(time_regex.group(1))
            unit = time_regex.group(2)
            if "sec" in unit:
                delay_seconds = int(qty)
                detected_time_str = f"in {int(qty)} second{'s' if qty != 1 else ''}"
            elif "hour" in unit or "hr" in unit:
                delay_seconds = int(qty * 3600)
                detected_time_str = f"in {int(qty) if qty.is_integer() else qty} hour{'s' if qty != 1 else ''}"
            else:
                delay_seconds = int(qty * 60)
                detected_time_str = f"in {int(qty) if qty.is_integer() else qty} minute{'s' if qty != 1 else ''}"

    # 3. Extract task text - strip leading conversational phrasing
    recurrence = None
    if re.search(r"\b(?:every\s+day|everyday|daily)\b", clean):
        recurrence = "daily"
    elif re.search(r"\b(?:every\s+week|weekly)\b", clean):
        recurrence = "weekly"
    elif re.search(r"\b(?:every\s+month|monthly)\b", clean):
        recurrence = "monthly"
    elif re.search(r"\bcustom\b", clean):
        recurrence = "custom"
    elif re.search(r"\b(?:only\s+for\s+that\s+day|only\s+that\s+day|only\s+today|just\s+today|just\s+for\s+today|today\s+only|once)\b", clean):
        recurrence = "once"

    extracted = re.sub(
        r"^(?:(?:could|can|would|will)\s+you\s+)?(?:please\s+)?(?:sarah\s*,?\s*)?(?:remind\s+(?:me|us)?\s*(?:to|about|for)?|set\s+(?:a\s+)?(?:daily\s+|weekly\s+|monthly\s+|custom\s+)?reminder\s+(?:to|for|about)?|schedule\s+(?:a\s+)?(?:daily\s+|weekly\s+|monthly\s+|custom\s+)?(?:reminder|schedule)\s+(?:to|for)?)\s*",
        "",
        clean,
        flags=re.IGNORECASE
    ).strip()

    # Strip recurrence keywords from extracted task text
    extracted = re.sub(
        r"\b(?:every\s+day|everyday|daily|every\s+week|weekly|every\s+month|monthly|custom|only\s+for\s+that\s+day|only\s+that\s+day|only\s+today|just\s+today|just\s+for\s+today|today\s+only|once)\b",
        "",
        extracted,
        flags=re.IGNORECASE
    ).strip(" .,!?")

    # If time prefix is at the beginning (e.g. "at 4:30 pm to take pills", "in 3:00 to take pills")
    time_prefix = re.match(
        r"^(?:at|in|for|by|on)?\s*\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?\s*(?:to|about|for)?\s*",
        extracted,
        re.IGNORECASE
    )
    if time_prefix and time_prefix.end() > 0 and time_prefix.group(0).strip():
        cand = extracted[time_prefix.end():]
        if cand.strip():
            extracted = cand
    else:
        dur_prefix = re.match(r"^(?:in|for)?\s*\d+(?:\.\d+)?\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)\s*(?:to|about|for)?\s*", extracted, re.IGNORECASE)
        if dur_prefix:
            extracted = extracted[dur_prefix.end():]

    # If time suffix is at the end (e.g. "to turn off the lights in 11.50 am", "to take my pills in 3:00", "to take my pills at 3:00")
    extracted = re.sub(
        r"\b(?:at|in|for|by|on)\s+\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?.*$",
        "",
        extracted,
        flags=re.IGNORECASE
    ).strip()
    extracted = re.sub(
        r"\b\d{1,2}[:.]\d{2}\s*(?:am|pm|a\.m\.|p\.m\.)?.*$",
        "",
        extracted,
        flags=re.IGNORECASE
    ).strip()
    extracted = re.sub(
        r"\bin\s+\d+(?:\.\d+)?\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)\b.*$",
        "",
        extracted,
        flags=re.IGNORECASE
    ).strip(" .,!?")

    extracted = re.sub(r"^(?:to|about|for)\s+", "", extracted).strip(" .,!?")
    extracted = convert_first_person_to_second_person(extracted)

    if not extracted:
        extracted = "your scheduled reminder"

    return {
        "text": extracted,
        "delay_seconds": max(5, delay_seconds),
        "delay_label": detected_time_str,
        "is_clock_time": is_clock_time,
        "recurrence": recurrence
    }


def set_reminder(
    text: str,
    delay_seconds: Optional[int] = None,
    delay_minutes: Optional[float] = None,
    target_time: Optional[str] = None,
    session_id: str = "default_session",
    recurrence: Optional[str] = None
) -> Dict[str, Any]:
    """Create a persistent scheduled reminder in SQLite database."""
    text = convert_first_person_to_second_person(text)
    effective_seconds = delay_seconds
    if target_time and effective_seconds is None:
        effective_seconds = parse_target_clock_time(target_time)
    elif delay_minutes is not None and effective_seconds is None:
        effective_seconds = int(delay_minutes * 60)
    elif effective_seconds is None:
        effective_seconds = 600

    effective_seconds = max(5, effective_seconds)
    now_ts = time.time()
    due_dt = datetime.now() + timedelta(seconds=effective_seconds)
    # Round to nearest minute for clean clock presentation if within 15 seconds of a full minute
    round_dt = due_dt
    if effective_seconds >= 60:
        if round_dt.second >= 45:
            round_dt = round_dt + timedelta(seconds=(60 - round_dt.second))
        elif round_dt.second <= 15:
            round_dt = round_dt - timedelta(seconds=round_dt.second)
        round_dt = round_dt.replace(microsecond=0)
        due_ts = round_dt.timestamp()
    else:
        due_ts = now_ts + effective_seconds
    due_formatted = round_dt.strftime("%I:%M %p")
    due_iso = round_dt.isoformat()

    reminder_id = f"rem_{uuid.uuid4().hex[:8]}"
    stored_recurrence = recurrence or "once"

    storage.create_reminder(
        reminder_id=reminder_id,
        session_id=session_id,
        text=text,
        due_at_timestamp=due_ts,
        due_at_iso=due_iso,
        delay_seconds=effective_seconds,
        recurrence=stored_recurrence
    )

    minutes_calc = round(effective_seconds / 60, 1)
    if minutes_calc < 1:
        time_text = f"{effective_seconds} seconds"
    elif minutes_calc < 60:
        time_text = f"{int(minutes_calc) if minutes_calc.is_integer() else minutes_calc} minute{'s' if minutes_calc != 1 else ''}"
    elif minutes_calc < 1440:
        hours_calc = round(effective_seconds / 3600, 1)
        time_text = f"{int(hours_calc) if hours_calc.is_integer() else hours_calc} hour{'s' if hours_calc != 1 else ''}"
    else:
        days_calc = round(effective_seconds / 86400, 1)
        time_text = f"{int(days_calc) if days_calc.is_integer() else days_calc} day{'s' if days_calc != 1 else ''}"

    if recurrence is None:
        # Prompt user for recurrence choice
        feedback = f"Okay, I've set a reminder to '{text}' for {due_formatted} (in {time_text}). Would you like this reminder for daily, weekly, monthly, custom, or only for that day?"
    elif recurrence == "once":
        feedback = f"Okay, I've set a reminder to '{text}' for {due_formatted} (in {time_text}) for only that day."
    else:
        feedback = f"Okay, I've set a {recurrence} reminder to '{text}' for {due_formatted} (in {time_text})."

    return {
        "status": "success",
        "reminder_id": reminder_id,
        "text": text,
        "due_at": due_formatted,
        "due_timestamp": due_ts,
        "due_iso": due_iso,
        "delay_seconds": effective_seconds,
        "recurrence": stored_recurrence,
        "feedback": feedback
    }


def update_reminder_recurrence(
    reminder_id: str,
    recurrence: str,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """Update recurrence for an active reminder."""
    clean_rec = recurrence.lower().strip()
    if any(w in clean_rec for w in ["every day", "everyday", "daily"]):
        norm_rec = "daily"
        rec_label = "daily"
    elif any(w in clean_rec for w in ["every week", "weekly"]):
        norm_rec = "weekly"
        rec_label = "weekly"
    elif any(w in clean_rec for w in ["every month", "monthly"]):
        norm_rec = "monthly"
        rec_label = "monthly"
    elif "custom" in clean_rec:
        norm_rec = "custom"
        rec_label = "custom"
    elif any(w in clean_rec for w in ["only for that day", "only that day", "only today", "just today", "just for today", "today only", "once", "that day", "today", "for that day"]):
        norm_rec = "once"
        rec_label = "only for that day"
    else:
        norm_rec = "once"
        rec_label = "only for that day"

    success = storage.update_reminder_recurrence(reminder_id, norm_rec, session_id=session_id)
    if success:
        return {
            "status": "success",
            "reminder_id": reminder_id,
            "recurrence": norm_rec,
            "feedback": f"Got it, I've set this reminder for {rec_label}."
        }
    return {
        "status": "error",
        "reminder_id": reminder_id,
        "feedback": "I couldn't find the reminder to update."
    }


def list_reminders(session_id: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve all pending active reminders and schedules."""
    items = storage.get_active_reminders(session_id)
    recent_history = storage.get_recent_reminders_history(session_id, limit=5)
    now_ts = time.time()

    formatted = []
    for item in items:
        remaining_secs = max(0, int(item["due_at_timestamp"] - now_ts))
        remaining_mins = max(1, int(round(remaining_secs / 60)))
        dt = datetime.fromtimestamp(item["due_at_timestamp"])
        if dt.second >= 45:
            dt = dt + timedelta(seconds=(60 - dt.second))
        elif dt.second <= 15 and item.get("delay_seconds", 0) > 60:
            dt = dt - timedelta(seconds=dt.second)
        time_str = dt.strftime("%I:%M %p")
        task_label = convert_first_person_to_second_person(item["text"])
        formatted.append({
            "id": item["id"],
            "text": task_label,
            "due_at": time_str,
            "remaining_minutes": remaining_mins,
            "recurrence": item.get("recurrence", "once"),
            "created_at": item["created_at"]
        })

    recent_completed_formatted = []
    for r in recent_history:
        r_dt = datetime.fromtimestamp(r["due_at_timestamp"])
        r_time_str = r_dt.strftime("%I:%M %p")
        r_task = convert_first_person_to_second_person(r["text"])
        recent_completed_formatted.append({
            "id": r["id"],
            "text": r_task,
            "scheduled_time": r_time_str,
            "status": r.get("status"),
            "recurrence": r.get("recurrence", "once")
        })

    if not formatted:
        if recent_completed_formatted:
            last = recent_completed_formatted[0]
            if last["status"] in ["completed", "reminded", "acknowledged"]:
                speech = f"You have no active reminders right now. Your earlier reminder to '{last['text']}' was set for {last['scheduled_time']} today and has already completed."
            elif last["status"] == "cancelled":
                speech = f"You have no active reminders right now. Your earlier reminder to '{last['text']}' was cancelled."
            else:
                speech = "You have no active reminders or scheduled tasks right now."
        else:
            speech = "You have no active reminders or scheduled tasks right now."
    elif len(formatted) == 1:
        item = formatted[0]
        speech = f"You have 1 active reminder: '{item['text']}' scheduled for {item['due_at']} (in about {item['remaining_minutes']} minutes)."
    else:
        parts = [f"'{it['text']}' at {it['due_at']}" for it in formatted]
        speech = f"You have {len(formatted)} active reminders: {', '.join(parts)}."

    return {
        "status": "success",
        "count": len(formatted),
        "reminders": formatted,
        "recent_completed": recent_completed_formatted,
        "feedback": speech
    }


def parse_cancel_expression(query: str) -> str:
    """Extract cancel target keyword/task or time from user query or return 'all'."""
    clean = query.strip().lower()
    # Normalize speech typos
    clean = re.sub(r"\bturn of\b", "turn off", clean)
    # Strip polite prefixes and wake words
    clean = re.sub(r"^(?:(?:could|can|would|will)\s+you\s+)?(?:please\s+)?(?:sarah\s*,?\s*)?", "", clean).strip()
    # Strip trailing conversational timing/politeness like "now", "please", "right now", "immediately"
    clean = re.sub(r"\b(?:right\s+now|now|please|immediately|for\s+me)\b", "", clean).strip()

    # Generic cancellation of all reminders
    # e.g., "cancel reminder", "cancel reminders", "cancel my reminders", "clear all reminders", "cancel all", "no i just need to clear it"
    if re.fullmatch(r"(?:no\s*,?\s*)?(?:i\s+)?(?:just\s+)?(?:need|want)\s+to\s+(?:clear|cancel|delete|remove)\s+(?:it|that|them|all|everything)?.*", clean):
        return "all"
    if re.fullmatch(r"(?:cancel|clear|remove|delete)\s+(?:all\s+)?(?:the\s+|my\s+)?reminders?", clean):
        return "all"
    if clean in [
        "cancel", "cancel reminder", "cancel reminders", "cancel my reminder", "cancel my reminders",
        "clear reminder", "clear reminders", "cancel all", "cancel all reminders", "all", "everything",
        "cancel the reminder", "cancel the reminders", "clear it", "clear them", "cancel that",
        "no i just need to clear it", "just clear it", "i just need to clear it", "clear", "cancel that cancel that"
    ]:
        return "all"

    # Pattern 1: "cancel [x] reminder(s)" or "cancel the/my [x] reminder"
    # e.g. "cancel 4 pm reminder", "cancel oven reminder", "cancel the oven reminder", "cancel check the oven reminder", "cancel my porridge reminder"
    m1 = re.search(r"\b(?:cancel|clear|remove|delete)\s+(?:the\s+|my\s+)?(.+?)\s+reminders?\b", clean)
    if m1:
        target = m1.group(1).strip()
        if target in ["all", "all of my", "any", "every", ""]:
            return "all"
        return target

    # Pattern 2: "cancel reminder(s) to/for/about/on/at [x]"
    # e.g. "cancel reminder at 4 pm", "cancel reminder for 4 pm", "cancel reminder to check the oven", "cancel reminder for lights", "cancel reminder about porridge"
    m2 = re.search(r"\b(?:cancel|clear|remove|delete)\s+(?:the\s+|my\s+)?reminders?\s+(?:to\s+|for\s+|about\s+|on\s+|at\s+)?(.+)", clean)
    if m2:
        target = m2.group(1).strip(" .!?")
        if target in ["all", "everything", ""]:
            return "all"
        return target

    # Pattern 3: "cancel [x]" where x is a reminder task, time, or ID (e.g. "cancel 4 pm", "cancel check the oven")
    m3 = re.search(r"\b(?:cancel|clear|remove|delete)\s+(?:the\s+|my\s+)?(.+)", clean)
    if m3:
        target = m3.group(1).strip(" .!?")
        if target in ["reminder", "reminders", "all", "all reminders", "everything"]:
            return "all"
        return target

    return "all"


def cancel_reminder(reminder_id_or_keyword: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Cancel active reminder(s) by ID, keyword/task name, scheduled time, or cancel all active reminders."""
    clean_kw = (reminder_id_or_keyword or "").lower().strip()
    clean_kw = re.sub(r"\b(?:right\s+now|now|please|immediately|for\s+me)\b", "", clean_kw).strip()

    # 1. Cancel ALL reminders if requested or generic reminder(s)
    is_all = clean_kw in [
        "all", "everything", "all reminders", "all my reminders",
        "reminder", "reminders", "the reminder", "the reminders",
        "my reminder", "my reminders", "it", "that", "them", "clear it", "clear", ""
    ]
    if is_all:
        count = storage.clear_all_reminders(session_id)

        # Clear matching items in fired_reminders_log as well
        for item in fired_reminders_log:
            if not session_id or item.get("session_id") in [session_id, "default_session"]:
                item["acknowledged"] = True
                item["status"] = "cancelled"

        if count == 0:
            return {
                "status": "not_found",
                "cancelled_count": 0,
                "feedback": "You don't have any active reminders to cancel."
            }
        return {
            "status": "success",
            "cancelled_count": count,
            "feedback": f"Cancelled all your active reminders ({count} scheduled reminder{'s' if count != 1 else ''})."
        }

    # 2. Cancel by 'latest' or 'recent'
    if clean_kw in ["latest", "recent", "last"]:
        active = storage.get_active_reminders(session_id) or storage.get_active_reminders(None)
        if active:
            target = active[-1]
            storage.cancel_reminder(target["id"], session_id)
            storage.cancel_reminder(target["id"], None)
            for item in fired_reminders_log:
                if item.get("id") == target["id"]:
                    item["acknowledged"] = True
                    item["status"] = "cancelled"
            return {
                "status": "success",
                "cancelled_count": 1,
                "feedback": f"Cancelled your reminder to '{target['text']}'."
            }
        return {
            "status": "not_found",
            "cancelled_count": 0,
            "feedback": "You don't have any active reminders to cancel."
        }

    # 3. Retrieve active reminders
    active = storage.get_active_reminders(session_id)
    if not active and session_id:
        active = storage.get_active_reminders(None)

    if not active:
        return {
            "status": "not_found",
            "cancelled_count": 0,
            "feedback": f"I couldn't find an active reminder matching '{reminder_id_or_keyword}'."
        }

    # Clean filler words for keyword matching
    target_clean = re.sub(r"\b(?:the|my|a|an|to|for|about|reminder|reminders|at|on|clock|o'clock)\b", "", clean_kw).strip()
    target_clean = re.sub(r"\s+", " ", target_clean)
    if not target_clean:
        target_clean = clean_kw

    # Check if keyword represents a clock time (e.g. "4 pm", "4pm", "3:59 pm", "4:00", "16:00")
    time_target = None
    time_m = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\b", clean_kw)
    if time_m:
        h = int(time_m.group(1))
        m = int(time_m.group(2) or 0)
        merid = (time_m.group(3) or "").lower()
        if merid == "pm" and h < 12:
            h += 12
        elif merid == "am" and h == 12:
            h = 0
        time_target = (h, m, bool(merid))

    matching_reminders = []
    for rem in active:
        r_id = rem["id"].lower()
        r_text = rem["text"].lower()
        due_dt = datetime.fromtimestamp(rem["due_at_timestamp"])

        # 3a. Direct ID match
        if r_id == clean_kw or r_id == target_clean:
            matching_reminders.append(rem)
            continue

        # 3b. Scheduled time match (within 15 minutes window, e.g. 4 PM matches 3:59 PM or 4:00 PM)
        if time_target:
            th, tm, has_merid = time_target
            diff_mins = abs((due_dt.hour * 60 + due_dt.minute) - (th * 60 + tm))
            if not has_merid:
                diff_mins = min(diff_mins, abs(((due_dt.hour % 12) * 60 + due_dt.minute) - ((th % 12) * 60 + tm)))
            if diff_mins <= 15:
                matching_reminders.append(rem)
                continue

        # 3c. Text substring or keyword match
        if target_clean in r_text or clean_kw in r_text or r_text in target_clean:
            matching_reminders.append(rem)
            continue

        target_words = [w for w in target_clean.split() if len(w) >= 3]
        if target_words and any(w in r_text for w in target_words):
            matching_reminders.append(rem)
            continue

    # 3d. Fallback for single active reminder in system
    if not matching_reminders and len(active) == 1:
        if time_target:
            th, tm, has_merid = time_target
            sole_dt = datetime.fromtimestamp(active[0]["due_at_timestamp"])
            diff = abs((sole_dt.hour * 60 + sole_dt.minute) - (th * 60 + tm))
            if not has_merid:
                diff = min(diff, abs(((sole_dt.hour % 12) * 60 + sole_dt.minute) - ((th % 12) * 60 + tm)))
            if diff <= 60:
                matching_reminders.append(active[0])
        else:
            matching_reminders.append(active[0])

    if matching_reminders:
        cancelled_names = []
        for rem in matching_reminders:
            storage.cancel_reminder(rem["id"], session_id)
            for item in fired_reminders_log:
                if item.get("id") == rem["id"]:
                    item["acknowledged"] = True
                    item["status"] = "cancelled"
            cancelled_names.append(f"'{rem['text']}'")

        if len(cancelled_names) == 1:
            feedback = f"Cancelled your reminder to {cancelled_names[0]}."
        else:
            feedback = f"Cancelled {len(cancelled_names)} reminders: {', '.join(cancelled_names)}."

        return {
            "status": "success",
            "cancelled_count": len(cancelled_names),
            "cancelled_reminders": matching_reminders,
            "feedback": feedback
        }

    # Fallback to direct DB cancel by keyword / ID
    success = storage.cancel_reminder(clean_kw, session_id) or storage.cancel_reminder(target_clean, session_id)

    if success:
        return {
            "status": "success",
            "cancelled_count": 1,
            "feedback": f"Cancelled reminder matching '{reminder_id_or_keyword}'."
        }

    return {
        "status": "not_found",
        "cancelled_count": 0,
        "feedback": f"I couldn't find an active reminder matching '{reminder_id_or_keyword}'."
    }


def check_due_reminders(window_seconds: float = 120.0, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Poll database for any reminders that have reached their due time or were recently triggered."""
    now_ts = time.time()
    due_items = storage.get_due_or_recently_triggered_reminders(now_ts, window_seconds=window_seconds, session_id=session_id)
    triggered = []

    for item in due_items:
        if item.get("status") == "pending":
            storage.mark_reminder_triggered(item["id"])
        task_text = convert_first_person_to_second_person(item["text"])
        if task_text.lower().startswith("to "):
            task_text = task_text[3:].strip()
        item_data = {
            "id": item["id"],
            "session_id": item["session_id"],
            "text": task_text,
            "due_at": datetime.fromtimestamp(item["due_at_timestamp"]).strftime("%I:%M %p"),
            "triggered_at": item.get("reminded_at") or datetime.now().isoformat(),
            "triggered_timestamp": item["due_at_timestamp"],
            "speech": f"Reminder alert: It's time to {task_text}."
        }
        # Update or add in fired log
        existing = next((f for f in fired_reminders_log if f.get("id") == item["id"]), None)
        if not existing:
            fired_reminders_log.append(item_data)
        elif item.get("status") == "acknowledged" or existing.get("acknowledged"):
            item_data["acknowledged"] = True

        if not item_data.get("acknowledged"):
            triggered.append(item_data)
            logger.info(f"[REMINDER ALERT READY] ID: {item['id']} Session: {item['session_id']} Text: {item['text']}")

    return triggered


def acknowledge_reminder(reminder_id: str) -> bool:
    """Mark reminder as acknowledged so it will not be delivered again."""
    storage.mark_reminder_acknowledged(reminder_id)
    for item in fired_reminders_log:
        if item.get("id") == reminder_id:
            item["acknowledged"] = True
    return True


# Async Background Worker
_worker_task: Optional[asyncio.Task] = None
_worker_running: bool = False


async def _reminder_loop():
    logger.info("Reminder background worker started.")
    while _worker_running:
        try:
            check_due_reminders()
        except Exception as e:
            logger.error(f"Error in reminder worker loop: {e}")
        await asyncio.sleep(5)
    logger.info("Reminder background worker stopped.")


def start_reminder_worker() -> Optional[asyncio.Task]:
    global _worker_task, _worker_running
    if not _worker_running:
        _worker_running = True
        _worker_task = asyncio.create_task(_reminder_loop())
    return _worker_task


def stop_reminder_worker():
    global _worker_running, _worker_task
    _worker_running = False
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        _worker_task = None
