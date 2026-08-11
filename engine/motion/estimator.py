"""
AirOS Engine — Motion Estimator
Tracks hand position velocity, acceleration, and direction over time.
Uses a rolling history buffer. All computations are in normalized [0,1] coordinates.
"""

import time
import numpy as np
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Deque


@dataclass
class MotionSample:
    """A single motion history sample."""
    x: float
    y: float
    timestamp: float


@dataclass
class MotionState:
    """Current motion state of a hand."""
    position: np.ndarray = field(default_factory=lambda: np.zeros(2))
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(2))
    speed: float = 0.0
    direction: np.ndarray = field(default_factory=lambda: np.zeros(2))  # unit vector
    acceleration: np.ndarray = field(default_factory=lambda: np.zeros(2))
    
    # Derived motion characteristics
    is_moving_up: bool = False
    is_moving_down: bool = False
    is_moving_left: bool = False
    is_moving_right: bool = False

    # Displacement over a longer window (for swipe detection)
    displacement_short: np.ndarray = field(default_factory=lambda: np.zeros(2))   # ~0.1s
    displacement_medium: np.ndarray = field(default_factory=lambda: np.zeros(2))  # ~0.3s
    displacement_long: np.ndarray = field(default_factory=lambda: np.zeros(2))    # ~0.5s


class MotionEstimator:
    """
    Estimates velocity, acceleration, and displacement from position history.
    
    Uses a rolling deque. The window size determines how much history is kept.
    All positions should be in normalized [0,1] image coordinates.
    """

    # Movement threshold — below this speed, consider the hand stationary
    MOVEMENT_THRESHOLD = 0.005  # normalized units/second

    # Direction threshold — minimum speed to consider direction meaningful
    DIRECTION_THRESHOLD = 0.01

    def __init__(self, history_size: int = 90):
        """
        Args:
            history_size: Number of samples to keep (90 @ 30fps = 3 seconds).
        """
        self._history: Deque[MotionSample] = deque(maxlen=history_size)
        self._state = MotionState()
        self._prev_velocity = np.zeros(2)

    def update(self, x: float, y: float, timestamp: Optional[float] = None) -> MotionState:
        """
        Add a new position sample and update motion estimates.
        
        Args:
            x, y: Normalized position [0, 1]
            timestamp: Monotonic timestamp in seconds (uses time.monotonic() if None)
        
        Returns:
            Updated MotionState
        """
        if timestamp is None:
            timestamp = time.monotonic()

        sample = MotionSample(x=x, y=y, timestamp=timestamp)
        self._history.append(sample)

        if len(self._history) < 2:
            self._state.position = np.array([x, y])
            return self._state

        self._state.position = np.array([x, y])

        # Velocity from last 2 samples (instantaneous)
        prev = self._history[-2]
        dt = timestamp - prev.timestamp
        if dt > 1e-6:
            dx = x - prev.x
            dy = y - prev.y
            self._state.velocity = np.array([dx / dt, dy / dt])
            self._state.speed = float(np.linalg.norm(self._state.velocity))
        else:
            self._state.velocity = np.zeros(2)
            self._state.speed = 0.0

        # Acceleration from velocity change
        dt_accel = dt
        if dt_accel > 1e-6:
            self._state.acceleration = (self._state.velocity - self._prev_velocity) / dt_accel
        self._prev_velocity = self._state.velocity.copy()

        # Direction (unit vector) — only meaningful above threshold
        if self._state.speed > self.DIRECTION_THRESHOLD:
            self._state.direction = self._state.velocity / (self._state.speed + 1e-8)
        # else keep last direction

        # Directional flags (using velocity, not just direction)
        vy = self._state.velocity[1]
        vx = self._state.velocity[0]
        self._state.is_moving_up = vy < -self.MOVEMENT_THRESHOLD
        self._state.is_moving_down = vy > self.MOVEMENT_THRESHOLD
        self._state.is_moving_left = vx < -self.MOVEMENT_THRESHOLD
        self._state.is_moving_right = vx > self.MOVEMENT_THRESHOLD

        # Displacement windows
        now = timestamp
        self._state.displacement_short = self._compute_displacement(now, 0.1)
        self._state.displacement_medium = self._compute_displacement(now, 0.3)
        self._state.displacement_long = self._compute_displacement(now, 0.5)

        return self._state

    def _compute_displacement(self, now: float, window_seconds: float) -> np.ndarray:
        """
        Compute displacement from window_seconds ago to now.
        Finds the oldest sample within the time window.
        """
        cutoff = now - window_seconds
        # Find first sample at or after cutoff
        reference = None
        for sample in self._history:
            if sample.timestamp >= cutoff:
                reference = sample
                break

        if reference is None:
            return np.zeros(2)

        current_pos = self._state.position
        ref_pos = np.array([reference.x, reference.y])
        return current_pos - ref_pos

    def get_state(self) -> MotionState:
        """Return the current motion state."""
        return self._state

    def reset(self):
        """Clear history (call when tracking is lost)."""
        self._history.clear()
        self._state = MotionState()
        self._prev_velocity = np.zeros(2)

    def get_history_seconds(self) -> float:
        """Returns how many seconds of history are available."""
        if len(self._history) < 2:
            return 0.0
        return self._history[-1].timestamp - self._history[0].timestamp
