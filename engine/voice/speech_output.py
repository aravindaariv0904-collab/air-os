"""
AirOS Engine — Speech Output (TTS)
Local Windows speech synthesis via SAPI (win32com). No network required.
Falls back to pyttsx3 if win32com is unavailable.
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class SpeechOutput:
    """Local TTS with a small speak queue (never blocks the real-time loop)."""

    def __init__(self):
        self._engine = None
        self._engine_type = None
        self._available = False
        self._lock = threading.Lock()
        self._init_engine()

    def _init_engine(self):
        try:
            import win32com.client
            self._engine = win32com.client.Dispatch("SAPI.SpVoice")
            self._engine.Rate = 0
            self._engine_type = "sapi"
            self._available = True
            return
        except Exception as e:
            logger.debug(f"SAPI unavailable: {e}")
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine_type = "pyttsx3"
            self._available = True
        except Exception as e:
            logger.debug(f"pyttsx3 unavailable: {e}")
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def set_rate(self, rate: int):
        if not self._available:
            return
        try:
            if self._engine_type == "sapi":
                self._engine.Rate = rate
            else:
                self._engine.setProperty("rate", rate)
        except Exception:
            pass

    def speak(self, text: str) -> bool:
        """Speak synchronously (call from the assistant thread)."""
        if not self._available or not text:
            return False
        try:
            with self._lock:
                if self._engine_type == "sapi":
                    self._engine.Speak(text, 1)  # SVSFlagsAsync=1
                    self._engine.WaitUntilDone(-1)
                else:
                    self._engine.say(text)
                    self._engine.runAndWait()
            return True
        except Exception as e:
            logger.warning(f"TTS failed: {e}")
            return False
