"""
AirOS Engine — Intent Parser
Deterministic natural-language parser converting transcribed speech into
structured intents for the ActionExecutor.

Example:
    "open settings"          -> {skill: "open_app", params: {app: "settings"}}
    "close the claude tab"   -> {skill: "close_browser_tab", params: {target: "claude"}}
    "increase the volume"    -> {skill: "volume", params: {action: "up"}}
    "set volume to fifty"    -> {skill: "volume", params: {action: "set", value: 50}}

Routing is deterministic first; no LLM is required for core commands.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

from engine.actions.skills import APP_ALIASES

logger = logging.getLogger(__name__)

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100,
}


@dataclass
class ParsedIntent:
    skill: str = ""
    params: Dict = field(default_factory=dict)
    confidence: float = 0.5
    raw_text: str = ""
    recognized: bool = False

    def to_dict(self) -> dict:
        return {
            "skill": self.skill,
            "params": self.params,
            "confidence": round(self.confidence, 3),
            "raw_text": self.raw_text,
            "recognized": self.recognized,
        }


def _norm(text: str) -> str:
    """Normalize transcript: lowercase, collapse whitespace, strip fillers."""
    text = text.lower()
    text = re.sub(r"\b(please|hey|okay|ok|the|a|an|can you|could you|would you|will you|just|maybe|kindly)\b", " ", text)
    text = re.sub(r"[^\w\s%]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(" windows", " ").replace(" browser", " ").strip()
    return text


def _parse_number(text: str) -> Optional[int]:
    """Parse an integer from a word phrase like 'fifty' or '50' or 'one hundred'."""
    m = re.search(r"(\d{1,3})", text)
    if m:
        return int(m.group(1))
    words = re.findall(r"[a-z]+", text)
    start = None
    for idx, w in enumerate(words):
        if w in NUMBER_WORDS:
            start = idx
            break
    if start is None:
        return None
    words = words[start:]
    total = 0
    current = 0
    for w in words:
        if w in NUMBER_WORDS:
            v = NUMBER_WORDS[w]
            if v == 100:
                if current == 0:
                    current = 1
                total += current * 100
                current = 0
            else:
                current += v
        else:
            break
    total += current
    return total if total > 0 else None


def _match_app(text: str) -> Optional[str]:
    """Match an app alias as a whole word inside the text (longest alias first)."""
    for alias in sorted(APP_ALIASES.keys(), key=len, reverse=True):
        if re.search(r"\b" + re.escape(alias) + r"\b", text):
            return alias
    return None


def parse_intent(transcript: str) -> ParsedIntent:
    """Parse a transcript into a structured intent."""
    text = _norm(transcript)
    raw = transcript.strip()
    if not text:
        return ParsedIntent(recognized=False, raw_text=raw)

    # --- Screenshot --------------------------------------------------
    if re.search(r"\bscreenshot\b|take a shot|screen shot|capture( the)? (full |entire |whole )?screen|snapshot", text):
        target = "all" if "full screen" in text or "fullscreen" in text or "entire screen" in text or "whole screen" in text else "active"
        return ParsedIntent("screenshot", {"target": target}, 0.92, raw, True)

    # --- Volume ------------------------------------------------------
    if re.search(r"\bmute\b", text):
        return ParsedIntent("volume", {"action": "mute"}, 0.92, raw, True)
    if re.search(r"\bunmute\b", text):
        return ParsedIntent("volume", {"action": "unmute"}, 0.92, raw, True)
    if re.search(r"\bset.*volume", text) or re.search(r"\bvolume.*set\b", text) or re.search(r"\bset volume to\b", text):
        value = _parse_number(text)
        if value is not None:
            return ParsedIntent("volume", {"action": "set", "value": value}, 0.9, raw, True)
    if re.search(r"\bincrease|turn up|volume up|raise", text) and "volume" in text:
        return ParsedIntent("volume", {"action": "up"}, 0.9, raw, True)
    if re.search(r"\bdecrease|turn down|volume down|lower", text) and "volume" in text:
        return ParsedIntent("volume", {"action": "down"}, 0.9, raw, True)
    if re.search(r"\bvolume up\b", text):
        return ParsedIntent("volume", {"action": "up"}, 0.9, raw, True)
    if re.search(r"\bvolume down\b", text):
        return ParsedIntent("volume", {"action": "down"}, 0.9, raw, True)

    # --- Media -------------------------------------------------------
    if re.search(r"\bplay|pause music|resume", text):
        return ParsedIntent("media", {"action": "play_pause"}, 0.8, raw, True)
    if re.search(r"\bnext (song|track|video)\b", text):
        return ParsedIntent("media", {"action": "next"}, 0.88, raw, True)
    if re.search(r"\bprevious (song|track|video)\b|last song", text):
        return ParsedIntent("media", {"action": "previous"}, 0.88, raw, True)

    # --- Scroll ------------------------------------------------------
    if re.search(r"\bscroll down|scroll below", text):
        return ParsedIntent("scroll", {"direction": "down"}, 0.9, raw, True)
    if re.search(r"\bscroll up|scroll above", text):
        return ParsedIntent("scroll", {"direction": "up"}, 0.9, raw, True)

    # --- Close tab / window ------------------------------------------
    m = re.search(r"\bclose (?:the )?(?:a )?(.+?) tab\b", text)
    if m:
        target = _norm(m.group(1))
        if target and target not in ("this", "that", "current", "active"):
            return ParsedIntent("close_browser_tab", {"target": target}, 0.9, raw, True)
        return ParsedIntent("close_browser_tab", {}, 0.85, raw, True)
    if re.search(r"\bclose (?:this|that|the) (?:browser )?tab\b", text):
        return ParsedIntent("close_browser_tab", {}, 0.85, raw, True)
    if re.search(r"\bclose tab\b", text):
        return ParsedIntent("close_browser_tab", {}, 0.85, raw, True)
    if re.search(r"\bclose (?:this|that|the) window\b|\bclose window\b", text):
        return ParsedIntent("close_window", {}, 0.85, raw, True)
    if re.search(r"\bclose (?:the )?(.+?)( window)?\b", text):
        target = _norm(re.search(r"\bclose (?:the )?(.+?)$", text).group(1))
        if target:
            # "close Claude" -> try closing the Claude tab/window
            return ParsedIntent("close_browser_tab", {"target": target}, 0.8, raw, True)

    # --- Window management -------------------------------------------
    if re.search(r"\bminimize", text):
        return ParsedIntent("minimize_window", {}, 0.88, raw, True)
    if re.search(r"\bmaximize", text):
        return ParsedIntent("maximize_window", {}, 0.88, raw, True)
    if re.search(r"\bswitch to (?:the )?(.+)", text):
        target = _norm(re.search(r"\bswitch to (?:the )?(.+)", text).group(1))
        if target:
            return ParsedIntent("switch_app", {"app": target}, 0.88, raw, True)
    if re.search(r"\bgo to (?:the )?(.+)", text):
        target = _norm(re.search(r"\bgo to (?:the )?(.+)", text).group(1))
        if target and target not in ("next tab", "previous tab"):
            return ParsedIntent("switch_app", {"app": target}, 0.82, raw, True)

    # --- Browser navigation ------------------------------------------
    if re.search(r"\bnew tab\b", text):
        return ParsedIntent("browser_navigation", {"action": "new_tab"}, 0.9, raw, True)
    if re.search(r"\bnext tab\b", text):
        return ParsedIntent("browser_navigation", {"action": "next_tab"}, 0.9, raw, True)
    if re.search(r"\breopen.*tab|reopen last tab", text):
        return ParsedIntent("browser_navigation", {"action": "reopen_tab"}, 0.9, raw, True)
    if re.search(r"\brefresh", text):
        return ParsedIntent("browser_navigation", {"action": "refresh"}, 0.85, raw, True)
    if re.search(r"\bgo back\b|\bnavigate back\b|\bback\b", text):
        return ParsedIntent("browser_navigation", {"action": "back"}, 0.8, raw, True)
    if re.search(r"\bgo forward\b|\bnavigate forward\b", text):
        return ParsedIntent("browser_navigation", {"action": "forward"}, 0.85, raw, True)

    # --- Settings pages ----------------------------------------------
    settings_pages = {
        "display": "display", "network": "network", "apps": "apps",
        "sound": "sound", "personalization": "personalization",
        "privacy": "privacy", "update": "update", "bluetooth": "bluetooth",
        "wifi": "network", "wallpaper": "personalization",
        "about": "about",
    }
    m = re.search(r"\b(?:open )?(display|network|wifi|apps|sound|personalization|privacy|update|bluetooth|wallpaper|about) settings\b", text)
    if m:
        page = m.group(1)
        return ParsedIntent("system_settings_open", {"page": settings_pages.get(page, page)}, 0.9, raw, True)

    # --- Open app / switch app ----------------------------------------
    if re.search(r"\bopen\b", text):
        after = re.sub(r"^.*?\bopen\b", "", text).strip()
        app = _match_app(after) or _match_app(text)
        if app:
            return ParsedIntent("open_app", {"app": app}, 0.9, raw, True)

    # --- Type text ----------------------------------------------------
    if re.search(r"\btype\b|write this|type text", text):
        after = re.sub(r"^.*?\b(type|write)\b", "", text).strip()
        if after:
            return ParsedIntent("type_text", {"text": after}, 0.7, raw, True)

    # --- Fallback: open known app by name -----------------------------
    app = _match_app(text)
    if app:
        return ParsedIntent("open_app", {"app": app}, 0.7, raw, True)

    return ParsedIntent(recognized=False, raw_text=raw)
