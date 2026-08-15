"""
AirOS Engine — Local Speech Recognition (Vosk)
Offline command recognition using the Vosk small English model.
The same recognizer is used for wake-word spotting and command capture.

Vosk is 100% local (no network calls) and works from a bundled model.
"""

import json
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def find_vosk_model() -> Optional[str]:
    """Locate a bundled Vosk model directory."""
    from engine.resources import resource_path

    candidates = [
        os.path.join("assets", "models", "vosk-model-small-en-us-0.15"),
        os.path.join("assets", "models", "vosk"),
    ]
    if getattr(__import__("sys"), "frozen", False):
        candidates.append(resource_path(os.path.join("assets", "models", "vosk-model-small-en-us-0.15")))
        candidates.append(resource_path(os.path.join("assets", "models", "vosk")))
    for c in candidates:
        if os.path.exists(os.path.join(c, "am", "final.mdl")) or os.path.exists(os.path.join(c, "conf", "model.conf")):
            return c
    # fallback: check env
    env = os.environ.get("AIROS_VOSK_MODEL")
    if env and os.path.isdir(env):
        return env
    return None


class VoskRecognizer:
    """Wraps a Vosk KaldiRecognizer with a consistent API."""

    def __init__(self, model_path: Optional[str] = None, sample_rate: int = 16000):
        self._sample_rate = sample_rate
        self._model = None
        self._recognizer = None
        self._model_path = model_path or find_vosk_model()
        self.initialized = False

    def initialize(self) -> bool:
        if self.initialized:
            return True
        try:
            from vosk import Model, KaldiRecognizer
        except ImportError as e:
            logger.warning(f"Vosk not installed: {e}")
            return False
        if not self._model_path or not os.path.isdir(self._model_path):
            logger.warning("Vosk model directory not found")
            return False
        try:
            self._model = Model(self._model_path)
            self._recognizer = KaldiRecognizer(self._model, self._sample_rate)
            self._recognizer.SetWords(False)
            self.initialized = True
            logger.info(f"Vosk recognizer initialized ({self._model_path})")
            return True
        except Exception as e:
            logger.warning(f"Vosk init failed: {e}")
            return False

    def accept_waveform(self, frame_bytes: bytes) -> bool:
        """Feed audio; returns True if a final utterance became available."""
        if not self.initialized:
            return False
        try:
            return self._recognizer.AcceptWaveform(frame_bytes) == True  # noqa: E712
        except Exception as e:
            logger.debug(f"AcceptWaveform error: {e}")
            return False

    def partial_text(self) -> str:
        """Text recognized so far in the current utterance."""
        if not self.initialized:
            return ""
        try:
            data = json.loads(self._recognizer.PartialResult())
            return data.get("partial", "") or ""
        except Exception:
            return ""

    def final_text(self) -> str:
        """Flush and return the final text of the current utterance."""
        if not self.initialized:
            return ""
        try:
            data = json.loads(self._recognizer.FinalResult())
            return data.get("text", "") or ""
        except Exception:
            return ""

    def result_text(self) -> str:
        """Get an intermediate final result without resetting."""
        if not self.initialized:
            return ""
        try:
            data = json.loads(self._recognizer.Result())
            return data.get("text", "") or ""
        except Exception:
            return ""
