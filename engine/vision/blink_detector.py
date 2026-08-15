"""
AirOS Engine — Blink Detector
Detects individual blinks from Eye Aspect Ratio (EAR) and recognizes a
deliberate TRIPLE-BLINK sequence (the primary eye command).

State machine:
    IDLE -> CLOSED (ear below threshold)
    CLOSED -> OPEN  : one blink (validated by closed-duration range)
    blinks are timestamped; a sequence of 3 blinks inside `sequence_window`
    fires TRIPLE_BLINK -> COOLDOWN -> IDLE

Natural blinking must not repeatedly trigger screenshots:
  - minimum closed duration (ignore ultra-short glitches)
  - maximum closed duration (ignore long closed-eye states, e.g. squinting)
  - minimum open duration between blinks
  - refractory / cooldown period after a confirmed triple blink
"""

import time
import logging
from dataclasses import dataclass
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class BlinkState:
    eye_state: str = "OPEN"          # OPEN | CLOSED
    ear: float = 1.0                 # latest eye aspect ratio
    face_present: bool = False
    blink_count: int = 0             # total single blinks (this session)
    blink_rate_bpm: float = 0.0      # rolling blinks per minute
    triple_blink_count: int = 0
    last_blink_at: float = 0.0
    last_event: str = "none"         # none | blink | triple_blink


class BlinkDetector:
    def __init__(
        self,
        ear_threshold: float = 0.21,
        min_closed_ms: float = 40.0,
        max_closed_ms: float = 400.0,
        min_open_ms: float = 150.0,
        sequence_window_ms: float = 2000.0,
        cooldown_ms: float = 4000.0,
        min_confidence: float = 0.7,
    ):
        self.ear_threshold = ear_threshold
        self.min_closed_ms = min_closed_ms
        self.max_closed_ms = max_closed_ms
        self.min_open_ms = min_open_ms
        self.sequence_window_ms = sequence_window_ms
        self.cooldown_ms = cooldown_ms
        self.min_confidence = min_confidence

        self._eye_state = "OPEN"
        self._state_entered: float = 0.0
        self._open_since: float = 0.0
        self._blink_ts: List[float] = []       # recent blink timestamps
        self._blink_rate_window: List[float] = []
        self._last_trigger_ts: float = 0.0
        self._triple_count = 0
        self._single_count = 0
        self._last_event = "none"
        self._last_ear = 1.0
        self._last_blink_at = 0.0
        self._blink_rate = 0.0
        self._face_present = False
        self.reset()

    def reset(self):
        self._eye_state = "OPEN"
        self._state_entered = time.monotonic()
        self._open_since = self._state_entered
        self._blink_ts = []
        self._blink_rate_window = []
        self._last_trigger_ts = 0.0

    def _in_cooldown(self, now: float) -> bool:
        return (now - self._last_trigger_ts) < (self.cooldown_ms / 1000.0)

    def update(
        self,
        ear: float,
        face_present: bool,
        timestamp: Optional[float] = None,
    ) -> BlinkState:
        """
        Feed one frame of eye aspect ratio.
        Returns the latest BlinkState; caller inspects last_event.
        """
        now = timestamp if timestamp is not None else time.monotonic()
        self._last_ear = ear
        self._face_present = face_present

        closed = face_present and (ear < self.ear_threshold)

        if closed and self._eye_state == "OPEN":
            # transition OPEN -> CLOSED
            open_duration = (now - self._state_entered) * 1000.0
            # require a minimum open duration before allowing a new blink
            if open_duration >= self.min_open_ms:
                self._eye_state = "CLOSED"
                self._state_entered = now
        elif not closed and self._eye_state == "CLOSED":
            # transition CLOSED -> OPEN : candidate blink
            closed_duration = (now - self._state_entered) * 1000.0
            self._eye_state = "OPEN"
            self._state_entered = now
            if self.min_closed_ms <= closed_duration <= self.max_closed_ms:
                self._register_blink(now)

        self._prune_blinks(now)
        self._update_rate(now)
        return self.get_state()

    def _register_blink(self, now: float):
        self._single_count += 1
        self._last_event = "blink"
        self._last_blink_at = now
        self._blink_ts.append(now)

        if self._in_cooldown(now):
            return
        # triple blink: 3 blinks within the sequence window
        recent = [t for t in self._blink_ts if (now - t) * 1000.0 <= self.sequence_window_ms]
        if len(recent) >= 3:
            self._triple_count += 1
            self._last_event = "triple_blink"
            self._last_trigger_ts = now
            self._blink_ts = []
            logger.info(f"TRIPLE BLINK detected (count={self._triple_count})")

    def _prune_blinks(self, now: float):
        cutoff = now - self.sequence_window_ms / 1000.0
        self._blink_ts = [t for t in self._blink_ts if t >= cutoff]

    def _update_rate(self, now: float):
        window = 60.0
        cutoff = now - window
        self._blink_rate_window = [t for t in self._blink_rate_window if t >= cutoff]
        if len(self._blink_rate_window) > 200:
            self._blink_rate_window = self._blink_rate_window[-100:]
        self._blink_rate_window.append(now)
        # blinks per minute using a 30s rolling window
        if now > cutoff:
            recent = [t for t in self._blink_rate_window if (now - t) <= 30.0]
            self._blink_rate = (len(recent) / 30.0) * 60.0 if recent else 0.0
        else:
            self._blink_rate = 0.0

    def consume_event(self) -> str:
        """Return and clear the last event."""
        ev = self._last_event
        self._last_event = "none"
        return ev

    def get_state(self) -> BlinkState:
        now = time.monotonic()
        return BlinkState(
            eye_state=self._eye_state,
            ear=round(self._last_ear, 4),
            face_present=self._face_present,
            blink_count=self._single_count,
            blink_rate_bpm=round(getattr(self, "_blink_rate", 0.0), 1),
            triple_blink_count=self._triple_count,
            last_blink_at=self._last_blink_at,
            last_event=self._last_event,
        )

    def to_dict(self) -> dict:
        st = self.get_state()
        return {
            "eye_state": st.eye_state,
            "ear": st.ear,
            "face_present": st.face_present,
            "blink_count": st.blink_count,
            "blink_rate_bpm": st.blink_rate_bpm,
            "triple_blink_count": st.triple_blink_count,
            "last_event": st.last_event,
        }
