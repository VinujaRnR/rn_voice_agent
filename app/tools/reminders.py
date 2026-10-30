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
    """Parse clock time string like '4:30 p.m.', '4:30pm', '11.50 am', '16:30', '5 pm' and return delay in seconds."""
    now = now or datetime.now()
    clean = time_str.lower().replace("a.m.", "am").replace("p.m.", "pm").strip()
    m = re.search(r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?", clean)
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

    # 1. Normalize speech typos and dot time representation (e.g. "turn of" -> "turn off", "11.50 am" -> "11:50 am")
    clean = re.sub(r"\bturn of\b", "turn off", clean)
    clean = re.sub(r"\b(\d{1,2})\.(\d{2})\s*(am|pm|a\.m\.|p\.m\.)", r"\1:\2 \3", clean)
    clean = re.sub(r"\b(\d{1,2})\.(\d{2})\b", r"\1:\2", clean)

    delay_seconds = 600
    detected_time_str = "10 minutes"
    is_clock_time = False

    # 2. Check for clock time like "in 11.50 am", "at 4:30 pm", "for 11:50 am", "by 5 pm"
    clock_m = re.search(r"\b(?:at|in|for|by|on)?\s*(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.))\b", clean, re.IGNORECASE)
    if not clock_m:
        clock_m = re.search(r"\b(\d{1,2}[:.]\d{2}\s*(?:am|pm|a\.m\.|p\.m\.)?)\b", clean, re.IGNORECASE)

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
    extracted = re.sub(
        r"^(?:(?:could|can|would|will)\s+you\s+)?(?:please\s+)?(?:sarah\s*,?\s*)?(?:remind\s+(?:me|us)?\s*(?:to|about|for)?|set\s+(?:a\s+)?reminder\s+(?:to|for|about)?|schedule\s+(?:a\s+)?(?:reminder|schedule)\s+(?:to|for)?)\s*",
        "",
        clean,
        flags=re.IGNORECASE
    ).strip()

    # If time prefix is at the beginning (e.g. "at 4:30 pm to take pills")
    time_prefix = re.match(r"^(?:at|in|for|by|on)?\s*\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)\s*(?:to|about|for)?\s*", extracted, re.IGNORECASE)
    if time_prefix:
        extracted = extracted[time_prefix.end():]
    else:
        dur_prefix = re.match(r"^(?:in|for)?\s*\d+(?:\.\d+)?\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)\s*(?:to|about|for)?\s*", extracted, re.IGNORECASE)
        if dur_prefix:
            extracted = extracted[dur_prefix.end():]

    # If time suffix is at the end (e.g. "to turn off the lights in 11.50 am")
    extracted = re.sub(
        r"\b(?:at|in|for|by|on)\s+\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?.*$",
        "",
        extracted,
        flags=re.IGNORECASE
    ).strip()
    extracted = re.sub(
        r"\b\d{1,2}[:.]\d{2}\s*(?:am|pm|a\.m\.|p\.m\.).*$",
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
        dt = datetime.fromtimestamp(item["due_at_timestamp"])
        if dt.second >= 45:
            dt = dt + timedelta(seconds=(60 - dt.second))
        elif dt.second <= 15 and item.get("delay_seconds", 0) > 60:
            dt = dt - timedelta(seconds=dt.second)
        time_str = dt.strftime("%I:%M %p")
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
    # e.g., "cancel reminder", "cancel reminders", "cancel my reminders", "clear all reminders", "cancel all"
    if re.fullmatch(r"(?:cancel|clear|remove|delete)\s+(?:all\s+)?(?:the\s+|my\s+)?reminders?", clean):
        return "all"
    if clean in [
        "cancel", "cancel reminder", "cancel reminders", "cancel my reminder", "cancel my reminders",
        "clear reminder", "clear reminders", "cancel all", "cancel all reminders", "all", "everything",
        "cancel the reminder", "cancel the reminders"
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
        "my reminder", "my reminders", ""
    ]
    if is_all:
        count = storage.clear_all_reminders(session_id)
        if count == 0 and session_id:
            count = storage.clear_all_reminders(None)

        # Clear matching items in fired_reminders_log as well
        for item in fired_reminders_log:
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
            storage.cancel_reminder(rem["id"], None)
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
    if not success and session_id:
        success = storage.cancel_reminder(clean_kw, None) or storage.cancel_reminder(target_clean, None)

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


def check_due_reminders(window_seconds: float = 120.0) -> List[Dict[str, Any]]:
    """Poll database for any reminders that have reached their due time or were recently triggered."""
    now_ts = time.time()
    due_items = storage.get_due_or_recently_triggered_reminders(now_ts, window_seconds=window_seconds)
    triggered = []

    for item in due_items:
        if item.get("status") == "pending":
            storage.mark_reminder_triggered(item["id"])
        item_data = {
            "id": item["id"],
            "session_id": item["session_id"],
            "text": item["text"],
            "due_at": datetime.fromtimestamp(item["due_at_timestamp"]).strftime("%I:%M %p"),
            "triggered_at": item.get("reminded_at") or datetime.now().isoformat(),
            "triggered_timestamp": item["due_at_timestamp"],
            "speech": f"Reminder alert: It's time to {item['text']}."
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
