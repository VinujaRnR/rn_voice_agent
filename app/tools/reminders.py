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


def parse_target_clock_time(time_str: str, now: Optional[datetime] = None) -> int:
    """Parse clock time string like '4:30 p.m.', '4:30pm', '16:30', '5 pm' and return delay in seconds."""
    now = now or datetime.now()
    clean = time_str.lower().replace(".", "").strip()
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", clean)
    if not m:
        return 600

    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = m.group(3)

    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    elif not meridiem and hour < 7:
        if now.hour >= 12:
            hour += 12

    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    diff = (target - now).total_seconds()

    # If within 2 minutes in the past, treat as immediate
    if -120 <= diff <= 0:
        return 10
    # If more than 2 minutes in the past, assume next day
    if diff < -120:
        target += timedelta(days=1)
        diff = (target - now).total_seconds()

    return max(5, int(diff))


def parse_reminder_expression(query: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Parse reminder intent, task text, and duration/time from spoken or typed query."""
    now = now or datetime.now()
    q = query.strip()
    clean = q.lower()

    delay_seconds = 600
    detected_time_str = "10 minutes"
    is_clock_time = False

    # 1. Check for clock time like "in 4:30 p.m.", "at 4:30 pm", "at 5 pm"
    clock_m = re.search(r"\b(?:at|in|for|by)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.))\b", clean)
    if not clock_m:
        clock_m = re.search(r"\b(\d{1,2}:\d{2}\s*(?:am|pm|a\.m\.|p\.m\.)?)\b", clean)

    if clock_m:
        time_token = clock_m.group(1)
        delay_seconds = parse_target_clock_time(time_token, now)
        is_clock_time = True
        target_dt = now + timedelta(seconds=delay_seconds)
        time_fmt = target_dt.strftime("%I:%M %p")
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

    # 2. Extract task text - strip leading conversational phrasing
    extracted = re.sub(
        r"^(?:(?:could|can|would|will)\s+you\s+)?(?:please\s+)?(?:sarah\s*,?\s*)?(?:remind\s+me\s+(?:to|about|for)?|set\s+(?:a\s+)?reminder\s+(?:to|for|about)?|schedule\s+(?:a\s+)?(?:reminder|schedule)\s+(?:to|for)?)\s*",
        "",
        q,
        flags=re.IGNORECASE
    ).strip()

    # Strip time suffix (e.g. "in 4:30 p.m.", "at 5 pm", "in 10 minutes")
    extracted = re.sub(
        r"\b(?:at|in|for|by)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?.*$",
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

    if not extracted:
        extracted = "your scheduled reminder"

    return {
        "text": extracted,
        "delay_seconds": max(5, delay_seconds),
        "delay_label": detected_time_str,
        "is_clock_time": is_clock_time
    }


def set_reminder(
    text: str,
    delay_seconds: Optional[int] = None,
    delay_minutes: Optional[float] = None,
    target_time: Optional[str] = None,
    session_id: str = "default_session"
) -> Dict[str, Any]:
    """Create a persistent scheduled reminder in SQLite database."""
    effective_seconds = delay_seconds
    if target_time and effective_seconds is None:
        effective_seconds = parse_target_clock_time(target_time)
    elif delay_minutes is not None and effective_seconds is None:
        effective_seconds = int(delay_minutes * 60)
    elif effective_seconds is None:
        effective_seconds = 600

    effective_seconds = max(5, effective_seconds)
    now_ts = time.time()
    due_ts = now_ts + effective_seconds
    due_dt = datetime.now() + timedelta(seconds=effective_seconds)
    due_iso = due_dt.isoformat()
    due_formatted = due_dt.strftime("%I:%M %p")

    reminder_id = f"rem_{uuid.uuid4().hex[:8]}"

    storage.create_reminder(
        reminder_id=reminder_id,
        session_id=session_id,
        text=text,
        due_at_timestamp=due_ts,
        due_at_iso=due_iso,
        delay_seconds=effective_seconds
    )

    minutes_calc = round(effective_seconds / 60, 1)
    if minutes_calc < 1:
        time_text = f"{effective_seconds} seconds"
    elif minutes_calc.is_integer():
        time_text = f"{int(minutes_calc)} minute{'s' if minutes_calc != 1 else ''}"
    else:
        time_text = f"{minutes_calc} minutes"

    feedback = f"Okay, I've set a reminder to '{text}' for {due_formatted} (in {time_text})."

    return {
        "status": "success",
        "reminder_id": reminder_id,
        "text": text,
        "due_at": due_formatted,
        "due_timestamp": due_ts,
        "due_iso": due_iso,
        "delay_seconds": effective_seconds,
        "feedback": feedback
    }


def list_reminders(session_id: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve all pending active reminders and schedules."""
    items = storage.get_active_reminders(session_id)
    now_ts = time.time()

    formatted = []
    for item in items:
        remaining_secs = max(0, int(item["due_at_timestamp"] - now_ts))
        remaining_mins = max(1, int(round(remaining_secs / 60)))
        time_str = datetime.fromtimestamp(item["due_at_timestamp"]).strftime("%I:%M %p")
        formatted.append({
            "id": item["id"],
            "text": item["text"],
            "due_at": time_str,
            "remaining_minutes": remaining_mins,
            "created_at": item["created_at"]
        })

    if not formatted:
        speech = "You have no active reminders or scheduled tasks right now."
    elif len(formatted) == 1:
        item = formatted[0]
        speech = f"You have 1 reminder: '{item['text']}' scheduled for {item['due_at']} (in about {item['remaining_minutes']} minutes)."
    else:
        parts = [f"'{it['text']}' at {it['due_at']}" for it in formatted]
        speech = f"You have {len(formatted)} active reminders: {', '.join(parts)}."

    return {
        "status": "success",
        "count": len(formatted),
        "reminders": formatted,
        "feedback": speech
    }


def cancel_reminder(reminder_id_or_keyword: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Cancel an active reminder by ID or keyword."""
    clean_kw = reminder_id_or_keyword.lower().strip()
    if clean_kw in ["all", "everything"]:
        count = storage.clear_all_reminders(session_id)
        return {
            "status": "success",
            "cancelled_count": count,
            "feedback": f"Cleared {count} scheduled reminder{'s' if count != 1 else ''}."
        }

    if clean_kw in ["latest", "recent", "my reminder", "the reminder", "last"]:
        active = storage.get_active_reminders(session_id)
        if active:
            target_id = active[-1]["id"]
            target_text = active[-1]["text"]
            storage.cancel_reminder(target_id, session_id)
            return {
                "status": "success",
                "feedback": f"Cancelled your reminder to '{target_text}'."
            }
        return {
            "status": "not_found",
            "feedback": "You don't have any active reminders to cancel."
        }

    success = storage.cancel_reminder(reminder_id_or_keyword, session_id)
    if success:
        return {
            "status": "success",
            "feedback": f"Cancelled reminder matching '{reminder_id_or_keyword}'."
        }
    return {
        "status": "not_found",
        "feedback": f"I couldn't find an active reminder matching '{reminder_id_or_keyword}'."
    }


def check_due_reminders() -> List[Dict[str, Any]]:
    """Poll database for any reminders that have reached their due time."""
    now_ts = time.time()
    due_items = storage.get_due_reminders(now_ts)
    triggered = []

    for item in due_items:
        storage.mark_reminder_triggered(item["id"])
        item_data = {
            "id": item["id"],
            "session_id": item["session_id"],
            "text": item["text"],
            "due_at": datetime.fromtimestamp(item["due_at_timestamp"]).strftime("%I:%M %p"),
            "triggered_at": datetime.now().isoformat(),
            "speech": f"Reminder alert: It's time to {item['text']}."
        }
        fired_reminders_log.append(item_data)
        triggered.append(item_data)
        logger.info(f"[REMINDER FIRED] ID: {item['id']} Session: {item['session_id']} Text: {item['text']}")

    return triggered


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
