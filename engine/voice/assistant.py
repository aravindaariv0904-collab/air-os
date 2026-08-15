"""
AirOS Engine — Voice Assistant
Local voice assistant coordinator running on its own thread.

State machine:
    DISABLED -> LISTENING -> WAKE_DETECTED -> CAPTURING
    CAPTURING -> PROCESSING -> RESPONDING -> COOLDOWN -> LISTENING
    any state -> ERROR (auto recovers to LISTENING)

Flow: mic -> Vosk keyword spotting ("jarvis") -> command capture ->
      deterministic intent parse -> ActionExecutor -> verifier -> local TTS.

No network is used at any point.
"""

import logging
import threading
import time
from typing import Optional, Callable

from engine.voice.audio import MicrophoneStream, rms_level
from engine.voice.recognizer import VoskRecognizer
from engine.voice.speech_output import SpeechOutput
from engine.voice.intent import parse_intent

logger = logging.getLogger(__name__)

ST_DISABLED = "DISABLED"
ST_LISTENING = "LISTENING"
ST_WAKE_DETECTED = "WAKE_DETECTED"
ST_CAPTURING = "CAPTURING_COMMAND"
ST_PROCESSING = "PROCESSING"
ST_RESPONDING = "RESPONDING"
ST_COOLDOWN = "COOLDOWN"
ST_ERROR = "ERROR"

SILENCE_RMS = 500.0


class VoiceAssistant:
    """
    Coordinates local wake word, STT, intent parsing, action execution, and TTS.

    deps:
      executor: ActionExecutor
      on_event: callback(dict) for UI/IPC display (status snapshots)
    """

    def __init__(
        self,
        executor,
        on_event: Optional[Callable[[dict], None]] = None,
        wake_word: str = "jarvis",
        command_timeout_ms: int = 7000,
        silence_timeout_ms: int = 1400,
        tts_enabled: bool = True,
        wake_sensitivity: float = 0.6,
    ):
        self._executor = executor
        self._on_event = on_event
        self._wake_word = wake_word.lower()
        self._command_timeout = command_timeout_ms / 1000.0
        self._silence_timeout = silence_timeout_ms / 1000.0
        self._tts_enabled = tts_enabled
        self._wake_sensitivity = wake_sensitivity

        self._mic = MicrophoneStream()
        self._recognizer = VoskRecognizer()
        self._tts = SpeechOutput()

        self._state = ST_DISABLED
        self._enabled = False
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._proc_lock = threading.Lock()
        self._last_transcript = ""
        self._last_intent = None
        self._last_response = None
        self._wake_count = 0
        self._error = ""
        self._capture_audio_level = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def initialize(self) -> bool:
        """Prepare voice pipeline (model + mic). Returns True if usable."""
        if not self._recognizer.initialize():
            self._error = "Speech model unavailable"
            logger.warning(self._error)
            return False
        if not self._mic.start():
            self._error = "Microphone unavailable"
            logger.warning(self._error)
            return False
        return True

    def start(self) -> bool:
        """Start the assistant thread. Requires initialize() first."""
        if self._running:
            return True
        if not self._mic.available or not self._recognizer.initialized:
            ok = self.initialize()
            if not ok:
                return False
        self._running = True
        self._enabled = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="VoiceAssistant")
        self._thread.start()
        logger.info("Voice assistant started")
        return True

    def stop(self):
        self._running = False
        self._enabled = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._mic.stop()
        self._set_state(ST_DISABLED)
        logger.info("Voice assistant stopped")

    def set_enabled(self, enabled: bool):
        if enabled and not self._running:
            self.start()
        elif not enabled and self._running:
            self.stop()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def update_settings(
        self,
        wake_word: Optional[str] = None,
        command_timeout_ms: Optional[int] = None,
        silence_timeout_ms: Optional[int] = None,
        tts_enabled: Optional[bool] = None,
    ):
        if wake_word:
            self._wake_word = wake_word.strip().lower()
        if command_timeout_ms is not None:
            self._command_timeout = max(2.0, min(15.0, command_timeout_ms / 1000.0))
        if silence_timeout_ms is not None:
            self._silence_timeout = max(0.4, min(5.0, silence_timeout_ms / 1000.0))
        if tts_enabled is not None:
            self._tts_enabled = bool(tts_enabled)
        self._emit()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def _set_state(self, state: str):
        with self._lock:
            changed = self._state != state
            self._state = state
        if changed:
            self._emit()
            logger.info(f"Voice state: {state}")

    def get_status(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "enabled": self._enabled,
                "wake_word": self._wake_word,
                "last_transcript": self._last_transcript,
                "wake_count": self._wake_count,
                "error": self._error,
                "tts_available": self._tts.available,
                "mic_available": self._mic.available,
                "recognizer_initialized": self._recognizer.initialized,
                "audio_level": round(self._capture_audio_level, 1),
                "last_intent": self._last_intent,
                "last_response": self._last_response,
            }

    def _emit(self):
        if self._on_event:
            try:
                self._on_event(self.get_status())
            except Exception as e:
                logger.error(f"Voice event callback error: {e}")

    def send_text_command(self, text: str) -> Optional[dict]:
        """Process a text command as if it were spoken (UI/testing)."""
        self._last_transcript = text.strip()
        self._emit()
        return self._process_transcript(text)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def _loop(self):
        self._set_state(ST_LISTENING)
        last_capture_activity = 0.0
        capture_started = 0.0
        capture_parts: list = []
        last_partial = ""

        while self._running:
            frame = self._mic.read_bytes(timeout=0.25)
            if frame is None:
                continue

            audio_level = rms_level(frame)
            self._capture_audio_level = audio_level
            speech_active = audio_level > SILENCE_RMS

            # Feed Vosk
            utterance_done = self._recognizer.accept_waveform(frame)
            partial = self._recognizer.partial_text().strip().lower()

            state = self._state

            if state == ST_LISTENING:
                if self._wake_word in partial:
                    self._wake_count += 1
                    capture_parts = []
                    last_partial = ""
                    capture_started = time.monotonic()
                    last_capture_activity = capture_started
                    self._set_state(ST_WAKE_DETECTED)
                    if self._tts_enabled:
                        self._tts.speak("Yes?")
                    self._set_state(ST_CAPTURING)
                elif utterance_done:
                    # A full utterance ended without the wake word; reset recognizer text
                    self._recognizer.final_text()
                continue

            if state in (ST_WAKE_DETECTED, ST_CAPTURING):
                # Capture the command phrase
                if partial and partial != last_partial:
                    last_partial = partial
                    last_capture_activity = time.monotonic()
                if speech_active:
                    last_capture_activity = time.monotonic()
                if utterance_done:
                    final = self._recognizer.result_text()
                    if final:
                        capture_parts.append(final)

                now = time.monotonic()
                capture_elapsed = now - capture_started
                silence_elapsed = now - last_capture_activity

                combined = self._combine_capture(capture_parts, last_partial)
                if combined:
                    self._last_transcript = combined
                    self._emit()

                if (combined and silence_elapsed >= self._silence_timeout) or capture_elapsed >= self._command_timeout:
                    # finalize
                    final = self._recognizer.final_text()
                    if final:
                        capture_parts.append(final)
                    combined = self._combine_capture(capture_parts, last_partial)
                    combined = self._strip_wake(combined)
                    self._set_state(ST_PROCESSING)
                    self._last_transcript = combined
                    self._emit()
                    self._process_transcript(combined)
                    capture_parts = []
                    last_partial = ""
                    continue

            if state == ST_COOLDOWN:
                time.sleep(0.5)
                self._set_state(ST_LISTENING)
                continue

            if state == ST_ERROR:
                time.sleep(1.0)
                self._set_state(ST_LISTENING)
                continue

            if state == ST_DISABLED:
                time.sleep(0.2)

        # end while

    def _strip_wake(self, text: str) -> str:
        parts = text.split()
        while parts and parts[0].lower() == self._wake_word:
            parts = parts[1:]
        return " ".join(parts).strip()

    @staticmethod
    def _combine_capture(parts: list, partial: str) -> str:
        """Merge final + partial text into a single command string."""
        merged = " ".join(parts).strip()
        if partial and partial not in merged:
            merged = (merged + " " + partial).strip()
        return merged

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------
    def _process_transcript(self, transcript: str) -> Optional[dict]:
        """Parse a transcript, execute the intent, and respond."""
        with self._proc_lock:
            return self._process_transcript_locked(transcript)

    def _process_transcript_locked(self, transcript: str) -> Optional[dict]:
        if not transcript:
            return None
        intent = parse_intent(transcript)
        self._last_intent = intent.to_dict()
        self._emit()

        if not intent.recognized:
            self._respond("Sorry, I did not understand that command.")
            return None

        response = self._executor.execute(intent.skill, intent.params)
        self._last_response = {
            "skill": response.skill,
            "message": response.message,
            "ok": response.ok,
            "verified": response.verified,
            "ambiguous": response.ambiguous,
        }
        self._emit()

        if response.ambiguous:
            self._respond(response.message or "That is ambiguous.")
        elif response.ok:
            self._respond(response.message)
        else:
            self._respond(f"I could not do that. {response.message}")

        # brief cooldown so we don't re-trigger on our own TTS
        self._set_state(ST_COOLDOWN)
        return self._last_response

    def _respond(self, text: str):
        self._set_state(ST_RESPONDING)
        if self._tts_enabled and self._tts.available:
            self._tts.speak(text)
