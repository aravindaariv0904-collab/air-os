"""
AirOS Engine — Core Gesture Detectors
Geometric + temporal gesture detection for all system gestures.

Each detector is a stateful class with:
- update(features) → Optional[GestureEvent]
- reset() → None
- confirmation_frames counter
- confidence calculation

Rule: NEVER trigger from a single frame. All gestures require temporal confirmation.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum, auto

import numpy as np

from engine.landmarks.geometry import (
    normalized_pinch_distance,
    is_finger_extended,
    is_index_only,
    is_open_palm,
    index_tip_position,
    wrist_position,
    count_extended_fingers,
    WRIST, INDEX_TIP, THUMB_TIP, INDEX_MCP, MIDDLE_MCP
)
from engine.state.states import GestureType

logger = logging.getLogger(__name__)


@dataclass
class GestureEvent:
    """A confirmed gesture event ready for action dispatch."""
    gesture: GestureType
    confidence: float
    timestamp: float
    extra: dict = field(default_factory=dict)


# =============================================================================
# Pinch Detector (Click / Drag)
# =============================================================================

class PinchState(Enum):
    OPEN = auto()
    APPROACHING = auto()
    PINCHED = auto()


class PinchDetector:
    """
    Detects pinch gesture (index tip + thumb tip proximity).
    
    State machine:
      OPEN → APPROACHING (distance decreasing toward threshold)
      APPROACHING → PINCHED (confirmed for N frames)
      PINCHED → OPEN (distance above release threshold)
    
    The APPROACHING state prevents immediate re-triggering after release.
    """

    # Distance thresholds (normalized by hand scale)
    PINCH_THRESHOLD = 0.30    # Below this = pinching
    RELEASE_THRESHOLD = 0.45  # Above this = released (hysteresis)
    CONFIRM_FRAMES = 4        # Frames required to confirm pinch
    CONFIRM_DURATION = 0.10   # Minimum duration (seconds)

    def __init__(self):
        self._state = PinchState.OPEN
        self._confirm_count = 0
        self._pinch_start_time: Optional[float] = None
        self._last_distance = 1.0

    def update(self, landmarks: np.ndarray, timestamp: float) -> Optional[PinchState]:
        """
        Update pinch detection with new landmarks.
        Returns new PinchState if state changed, else None.
        """
        distance = normalized_pinch_distance(landmarks)
        self._last_distance = distance
        prev_state = self._state

        if self._state == PinchState.OPEN:
            if distance < self.PINCH_THRESHOLD * 1.5:
                self._state = PinchState.APPROACHING
                self._confirm_count = 1
            else:
                self._confirm_count = 0

        elif self._state == PinchState.APPROACHING:
            if distance < self.PINCH_THRESHOLD:
                self._confirm_count += 1
                if self._confirm_count >= self.CONFIRM_FRAMES:
                    self._state = PinchState.PINCHED
                    self._pinch_start_time = timestamp
            elif distance > self.RELEASE_THRESHOLD:
                self._state = PinchState.OPEN
                self._confirm_count = 0
            else:
                self._confirm_count = max(0, self._confirm_count - 1)

        elif self._state == PinchState.PINCHED:
            if distance > self.RELEASE_THRESHOLD:
                self._state = PinchState.OPEN
                self._confirm_count = 0
                self._pinch_start_time = None

        return self._state if self._state != prev_state else None

    @property
    def is_pinched(self) -> bool:
        return self._state == PinchState.PINCHED

    @property
    def is_approaching(self) -> bool:
        return self._state == PinchState.APPROACHING

    @property
    def pinch_distance(self) -> float:
        return self._last_distance

    @property
    def pinch_duration(self) -> float:
        if self._pinch_start_time is None:
            return 0.0
        return time.monotonic() - self._pinch_start_time

    def get_confidence(self) -> float:
        """Returns pinch confidence (0-1) based on distance and confirm count."""
        if not self.is_pinched:
            return 0.0
        dist_confidence = max(0.0, 1.0 - (self._last_distance / self.PINCH_THRESHOLD))
        frame_confidence = min(1.0, self._confirm_count / (self.CONFIRM_FRAMES * 2))
        return (dist_confidence * 0.6 + frame_confidence * 0.4)

    def reset(self):
        self._state = PinchState.OPEN
        self._confirm_count = 0
        self._pinch_start_time = None


# =============================================================================
# Scroll Detector
# =============================================================================

class ScrollDetector:
    """
    Detects vertical scroll gestures from hand velocity.
    
    Uses sustained vertical movement with velocity thresholds.
    Scroll intensity is proportional to speed.
    """

    # Velocity thresholds (normalized units / second)
    SCROLL_VELOCITY_THRESHOLD = 0.15   # Minimum vertical speed to trigger scroll
    SCROLL_CONFIRM_FRAMES = 3          # Frames of sustained movement required
    MAX_SCROLL_VELOCITY = 1.0          # Caps scroll speed at this value
    SCROLL_COOLDOWN = 0.08             # Seconds between scroll events (rate limiting)

    def __init__(self):
        self._confirm_up = 0
        self._confirm_down = 0
        self._last_scroll_time: float = 0.0

    def update(self, velocity_y: float, timestamp: float) -> Optional[GestureEvent]:
        """
        Update scroll detection with current vertical velocity.
        
        velocity_y > 0: hand moving DOWN (scroll down)
        velocity_y < 0: hand moving UP (scroll up)
        
        Note: MediaPipe Y increases downward, so negative Y = moving up in image.
        """
        # Rate limit
        if timestamp - self._last_scroll_time < self.SCROLL_COOLDOWN:
            return None

        speed = abs(velocity_y)
        if speed < self.SCROLL_VELOCITY_THRESHOLD:
            self._confirm_up = 0
            self._confirm_down = 0
            return None

        if velocity_y < -self.SCROLL_VELOCITY_THRESHOLD:  # Moving UP in image = scroll UP
            self._confirm_up += 1
            self._confirm_down = 0
            if self._confirm_up >= self.SCROLL_CONFIRM_FRAMES:
                intensity = min(speed / self.MAX_SCROLL_VELOCITY, 1.0)
                self._last_scroll_time = timestamp
                return GestureEvent(
                    gesture=GestureType.SCROLL_UP,
                    confidence=intensity,
                    timestamp=timestamp,
                    extra={"intensity": intensity, "velocity": velocity_y},
                )
        elif velocity_y > self.SCROLL_VELOCITY_THRESHOLD:  # Moving DOWN in image = scroll DOWN
            self._confirm_down += 1
            self._confirm_up = 0
            if self._confirm_down >= self.SCROLL_CONFIRM_FRAMES:
                intensity = min(speed / self.MAX_SCROLL_VELOCITY, 1.0)
                self._last_scroll_time = timestamp
                return GestureEvent(
                    gesture=GestureType.SCROLL_DOWN,
                    confidence=intensity,
                    timestamp=timestamp,
                    extra={"intensity": intensity, "velocity": velocity_y},
                )
        return None

    def reset(self):
        self._confirm_up = 0
        self._confirm_down = 0


# =============================================================================
# Swipe Detector
# =============================================================================

class SwipeDetector:
    """
    Detects intentional left/right swipe gestures.
    
    Requirements:
    - Minimum displacement in dominant direction
    - Minimum velocity
    - Displacement must be predominantly horizontal (not diagonal)
    - Temporal consistency (sustained movement, not jitter)
    - Cooldown between swipes
    """

    MIN_DISPLACEMENT = 0.18      # Minimum horizontal displacement (normalized)
    MIN_VELOCITY = 0.35          # Minimum horizontal velocity
    AXIS_RATIO = 2.0             # Horizontal displacement must be N× vertical
    CONFIRM_FRAMES = 4
    COOLDOWN = 0.6               # Seconds between swipe events (prevent rapid-fire)

    def __init__(self):
        self._last_swipe_time: float = 0.0
        self._left_count = 0
        self._right_count = 0
        self._tracking_start_x: Optional[float] = None
        self._tracking_start_y: Optional[float] = None

    def update(
        self,
        displacement_x: float,
        displacement_y: float,
        velocity_x: float,
        timestamp: float,
    ) -> Optional[GestureEvent]:
        """
        Evaluate swipe conditions.
        
        displacement_x/y: position change over ~0.3s window (medium window)
        velocity_x: current horizontal velocity
        """
        if timestamp - self._last_swipe_time < self.COOLDOWN:
            return None

        abs_dx = abs(displacement_x)
        abs_dy = abs(displacement_y)
        abs_vx = abs(velocity_x)

        # Check minimum conditions
        if abs_dx < self.MIN_DISPLACEMENT or abs_vx < self.MIN_VELOCITY:
            self._left_count = 0
            self._right_count = 0
            return None

        # Check that movement is predominantly horizontal
        if abs_dy > 0.001 and abs_dx / abs_dy < self.AXIS_RATIO:
            self._left_count = 0
            self._right_count = 0
            return None

        if displacement_x < -self.MIN_DISPLACEMENT and velocity_x < -self.MIN_VELOCITY:
            self._left_count += 1
            self._right_count = 0
            if self._left_count >= self.CONFIRM_FRAMES:
                self._left_count = 0
                self._last_swipe_time = timestamp
                confidence = min(abs_dx / (self.MIN_DISPLACEMENT * 2), 1.0)
                return GestureEvent(
                    gesture=GestureType.SWIPE_LEFT,
                    confidence=confidence,
                    timestamp=timestamp,
                    extra={"displacement": displacement_x, "velocity": velocity_x},
                )
        elif displacement_x > self.MIN_DISPLACEMENT and velocity_x > self.MIN_VELOCITY:
            self._right_count += 1
            self._left_count = 0
            if self._right_count >= self.CONFIRM_FRAMES:
                self._right_count = 0
                self._last_swipe_time = timestamp
                confidence = min(abs_dx / (self.MIN_DISPLACEMENT * 2), 1.0)
                return GestureEvent(
                    gesture=GestureType.SWIPE_RIGHT,
                    confidence=confidence,
                    timestamp=timestamp,
                    extra={"displacement": displacement_x, "velocity": velocity_x},
                )
        else:
            self._left_count = max(0, self._left_count - 1)
            self._right_count = max(0, self._right_count - 1)

        return None

    def reset(self):
        self._left_count = 0
        self._right_count = 0


# =============================================================================
# Open Palm Detector (PAUSE gesture)
# =============================================================================

class OpenPalmDetector:
    """
    Detects open palm held for a duration → PAUSE.
    All four fingers must be extended, hand relatively still.
    """

    CONFIRM_FRAMES = 8           # ~0.27s at 30fps before triggering
    HOLD_DURATION = 0.8          # Must hold for this long to activate
    STILL_VELOCITY_THRESHOLD = 0.12  # Palm must be relatively still

    def __init__(self):
        self._confirm_count = 0
        self._hold_start: Optional[float] = None
        self._active = False

    def update(
        self, landmarks: np.ndarray, speed: float, timestamp: float
    ) -> Optional[GestureEvent]:
        """Returns a PAUSE GestureEvent when open palm is held long enough."""
        palm_open = is_open_palm(landmarks)
        still_enough = speed < self.STILL_VELOCITY_THRESHOLD

        if palm_open and still_enough:
            self._confirm_count += 1
            if self._hold_start is None:
                self._hold_start = timestamp
            
            if (not self._active and
                    self._confirm_count >= self.CONFIRM_FRAMES and
                    (timestamp - self._hold_start) >= self.HOLD_DURATION):
                self._active = True
                return GestureEvent(
                    gesture=GestureType.OPEN_PALM,
                    confidence=0.92,
                    timestamp=timestamp,
                )
        else:
            self._confirm_count = max(0, self._confirm_count - 2)
            if self._confirm_count == 0:
                self._hold_start = None
            if not palm_open:
                self._active = False  # Deactivate when palm closed

        return None

    def reset(self):
        self._confirm_count = 0
        self._hold_start = None
        self._active = False


# =============================================================================
# Two-Hand Detector (Keyboard mode entry)
# =============================================================================

class TwoHandDetector:
    """
    Detects two hands held deliberately for keyboard mode entry.
    Requires both hands to be detected consistently for a hold duration.
    """

    CONFIRM_FRAMES = 15          # ~0.5s at 30fps
    HOLD_DURATION = 1.5          # Must hold for 1.5 seconds to enter keyboard
    COOLDOWN = 2.0               # Minimum time between activations

    def __init__(self):
        self._confirm_count = 0
        self._hold_start: Optional[float] = None
        self._last_activation: float = 0.0

    def update(self, num_hands: int, timestamp: float) -> Optional[GestureEvent]:
        """Returns a TWO_HANDS event when two hands are held consistently."""
        if timestamp - self._last_activation < self.COOLDOWN:
            return None

        if num_hands >= 2:
            self._confirm_count += 1
            if self._hold_start is None:
                self._hold_start = timestamp

            if (self._confirm_count >= self.CONFIRM_FRAMES and
                    (timestamp - self._hold_start) >= self.HOLD_DURATION):
                self._last_activation = timestamp
                self._confirm_count = 0
                self._hold_start = None
                return GestureEvent(
                    gesture=GestureType.TWO_HANDS,
                    confidence=0.90,
                    timestamp=timestamp,
                )
        else:
            # Decay if one hand disappears
            self._confirm_count = max(0, self._confirm_count - 3)
            if self._confirm_count == 0:
                self._hold_start = None

        return None

    def reset(self):
        self._confirm_count = 0
        self._hold_start = None
