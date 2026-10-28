"""Accent and Phonetic Normalizer.

Disambiguates and normalizes accent-induced phoneme distortions, regional pronunciation
variants (e.g. Sri Lankan / South Asian / non-rhotic English), and speech recognition errors
before intent parsing and tool routing.
"""
import re
from typing import List, Tuple

# Mapping of regex patterns to canonical domain terms
ACCENT_RULES: List[Tuple[re.Pattern, str]] = [
    # 1. Wake word variants at start of query (e.g. "Sierra", "Serah", "Sera", "Zarah")
    (
        re.compile(
            r"^(?:(?:hey|hi|ok|okay|hello)\s+)?\b(sarah|sierra|serrah|sarrah|serra|sarra|sarha|sahra|saira|serah|zarah|syrah|surah|sara|sera|zara|cera|zahra|zera|sayrah|sorah|sura|seira|sora)\b",
            re.IGNORECASE
        ),
        "Sarah"
    ),

    # 2. Testing farm lights phonetics (e.g. "fan lights", "firm lights", "form lights", "palm lights")
    (
        re.compile(r"\btesting\s+(?:farm|fan|form|firm|palm|fram|from|farms)\s+lights?\b", re.IGNORECASE),
        "testing farm lights"
    ),
    (
        re.compile(r"\b(?:farm|fan|form|firm|palm|fram)\s+lights?\b", re.IGNORECASE),
        "farm lights"
    ),

    # 3. Room lights phonetics (e.g. "rum lights", "room light", "rome lights")
    (
        re.compile(r"\b(?:room|rum|rome)\s+lights?\b", re.IGNORECASE),
        "room lights"
    ),

    # 4. Kitchen lights phonetics
    (
        re.compile(r"\bkitchen\s+(?:lights?|likes?|line)\b", re.IGNORECASE),
        "kitchen lights"
    ),

    # 5. Desk lamp phonetics
    (
        re.compile(r"\bdesk\s+(?:lamp|light|lamb|ramp)\b", re.IGNORECASE),
        "desk lamp"
    ),

    # 6. Location phonetics: Colombo / Sri Lanka
    (
        re.compile(r"\b(?:columbo|columba|calombo|calumba|kolombo|kolomba)\b", re.IGNORECASE),
        "Colombo"
    ),
    (
        re.compile(r"\b(?:srilanka|sri\s+lanka|shri\s+lanka)\b", re.IGNORECASE),
        "Sri Lanka"
    ),

    # 7. Command phonetics: turn on / turn off / switch on / switch off
    (
        re.compile(r"\b(?:tern|tunnel|tune|ten|danone|turn)\s+on\b", re.IGNORECASE),
        "turn on"
    ),
    (
        re.compile(r"\b(?:tern|tune|turned)\s+off\b", re.IGNORECASE),
        "turn off"
    ),
    (
        re.compile(r"\bturn\s+of\b", re.IGNORECASE),
        "turn off"
    ),
    (
        re.compile(r"\b(?:switch|switched)\s+of\b", re.IGNORECASE),
        "switch off"
    ),

    # 8. Weather phonetics
    (
        re.compile(r"\bwhether\s+(?:in|for|at|around)\b", re.IGNORECASE),
        "weather in"
    ),
    (
        re.compile(r"\bwhat\s+(?:is\s+the|is|the)\s+whether\b", re.IGNORECASE),
        "what is the weather"
    ),

    # 9. Time phonetics
    (
        re.compile(r"\bwhat\s+time\s+is\s+it\s+(?:in|at)\b", re.IGNORECASE),
        "what time is it in"
    )
]


def normalize_accent_transcript(text: str) -> str:
    """Normalize regional phonetics and speech recognition mishearings in text."""
    if not text:
        return ""

    cleaned = text.strip()

    # Apply canonical replacement rules
    for pattern, replacement in ACCENT_RULES:
        cleaned = pattern.sub(replacement, cleaned)

    # Normalize excessive spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned
