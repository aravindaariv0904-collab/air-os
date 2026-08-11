"""
AirOS — Virtual Keyboard
Overlay keyboard for air-tap text entry.

Layout: QWERTY with numbers, space, backspace, enter, shift.
Targeting: Index fingertip position maps to key.
Air-tap: Deliberate short Z-axis movement (or vertical approach) triggers key.

Limitations (honest):
- Target: short text entry (search queries, quick commands)
- NOT touch-typing speed
- Accuracy depends on hand stability and calibration
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict
import numpy as np

logger = logging.getLogger(__name__)


# ─── Keyboard Layout ─────────────────────────────────────────────────────────

KEYBOARD_ROWS = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
    ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
    ["A", "S", "D", "F", "G", "H", "J", "K", "L"],
    ["SHIFT", "Z", "X", "C", "V", "B", "N", "M", "⌫"],
    ["SPACE", "ENTER"],
]

SPECIAL_KEYS = {"⌫": "backspace", "SPACE": "space", "ENTER": "enter", "SHIFT": "shift"}

# Normalized layout bounds [0, 1] — the keyboard occupies the bottom portion of screen
KB_LEFT = 0.05
KB_RIGHT = 0.95
KB_TOP = 0.55     # Keyboard starts at 55% height (bottom half of interaction area)
KB_BOTTOM = 0.98
ROW_HEIGHT = (KB_BOTTOM - KB_TOP) / len(KEYBOARD_ROWS)


@dataclass
class KeyLayout:
    """A single key's layout information."""
    label: str
    norm_x: float      # Center X in normalized screen coords [0,1]
    norm_y: float      # Center Y
    width: float       # Width in normalized units
    height: float      # Height in normalized units
    action: str        # What to do when tapped


def build_keyboard_layout() -> List[KeyLayout]:
    """Build the full keyboard layout as normalized key positions.

    Each row distributes its width among keys using a weight per key so that
    hit areas never overlap: regular keys are 1 cell, SHIFT/BACKSPACE are
    1.5 cells, ENTER is 2.5 cells, SPACE is 5 cells. Gaps keep adjacent
    keys distinct.
    """
    # Row-level weights per label (cells). Regular keys default to 1.
    ROW_WEIGHTS = {
        "SHIFT": 1.5,
        "⌫": 1.5,
        "ENTER": 2.5,
        "SPACE": 5.0,
    }
    GAP = 0.006  # gap between keys (normalized units)

    keys = []
    for row_idx, row in enumerate(KEYBOARD_ROWS):
        y_center = KB_TOP + (row_idx + 0.5) * ROW_HEIGHT
        row_width = KB_RIGHT - KB_LEFT

        weights = [ROW_WEIGHTS.get(label, 1.0) for label in row]
        total_weight = sum(weights)
        key_height = ROW_HEIGHT * 0.85

        # Total gap space = (n_keys - 1) * GAP
        total_gaps = GAP * (len(row) - 1)
        avail_width = row_width - total_gaps
        cell = avail_width / total_weight

        x_cursor = KB_LEFT
        for label, weight in zip(row, weights):
            width = cell * weight
            x_center = x_cursor + width / 2
            action = SPECIAL_KEYS.get(label, label.lower())
            keys.append(KeyLayout(
                label=label,
                norm_x=x_center,
                norm_y=y_center,
                width=width,
                height=key_height,
                action=action,
            ))
            x_cursor += width + GAP

    return keys


# ─── Air Tap Detector ────────────────────────────────────────────────────────

class AirTapDetector:
    """
    Detects an intentional 'air tap' for virtual keyboard input.
    
    Air tap = deliberate short downward movement of index fingertip
    followed by quick upward return.
    
    Does NOT activate from hovering — requires explicit motion.
    Uses debouncing to prevent repeated activations from one tap.
    """

    # Tap detection parameters
    TAP_DOWN_THRESHOLD = 0.025    # Y movement required (downward in camera space)
    TAP_RETURN_THRESHOLD = 0.015  # Y return movement required
    TAP_MIN_DURATION = 0.05       # Minimum time for tap cycle (prevents noise)
    TAP_MAX_DURATION = 0.4        # Maximum time for tap cycle (too slow = not a tap)
    DEBOUNCE_TIME = 0.35          # Minimum time between successive taps on same key
    HOVER_CONFIRM_FRAMES = 3      # Frames finger must hover over key before tap is valid

    class TapPhase:
        IDLE = "idle"
        HOVERING = "hovering"
        TAPPING_DOWN = "tapping_down"
        TAPPING_UP = "tapping_up"

    def __init__(self):
        self._phase = self.TapPhase.IDLE
        self._peak_y: Optional[float] = None     # Lowest Y reached during down stroke
        self._start_y: Optional[float] = None    # Y when tap started
        self._tap_start_time: float = 0.0
        self._last_tap_time: Dict[str, float] = {}  # Per-key debounce
        self._hover_count: int = 0
        self._hovered_key: Optional[str] = None

    def update(
        self,
        fingertip_y: float,
        hovered_key: Optional[str],
        timestamp: float,
    ) -> Optional[str]:
        """
        Update with current fingertip Y position and which key is hovered.
        Returns the key's action string if a tap is confirmed, else None.
        """
        # Track hover for confirmation
        if hovered_key != self._hovered_key:
            self._hovered_key = hovered_key
            self._hover_count = 0
            self._phase = self.TapPhase.IDLE

        if hovered_key is None:
            self._hover_count = 0
            self._phase = self.TapPhase.IDLE
            return None

        self._hover_count += 1

        if self._phase == self.TapPhase.IDLE:
            if self._hover_count >= self.HOVER_CONFIRM_FRAMES:
                self._phase = self.TapPhase.HOVERING
                self._start_y = fingertip_y

        elif self._phase == self.TapPhase.HOVERING:
            # Detect downward movement (Y increases downward in image space)
            if self._start_y is not None and (fingertip_y - self._start_y) > self.TAP_DOWN_THRESHOLD:
                self._phase = self.TapPhase.TAPPING_DOWN
                self._peak_y = fingertip_y
                self._tap_start_time = timestamp

        elif self._phase == self.TapPhase.TAPPING_DOWN:
            if self._peak_y is not None:
                self._peak_y = max(self._peak_y, fingertip_y)  # Track maximum Y reached
            # Detect return movement (finger coming back up)
            if (self._peak_y is not None and
                    (self._peak_y - fingertip_y) > self.TAP_RETURN_THRESHOLD):
                tap_duration = timestamp - self._tap_start_time
                if self.TAP_MIN_DURATION <= tap_duration <= self.TAP_MAX_DURATION:
                    self._phase = self.TapPhase.HOVERING
                    self._start_y = fingertip_y
                    # Check debounce
                    last = self._last_tap_time.get(hovered_key, 0.0)
                    if timestamp - last >= self.DEBOUNCE_TIME:
                        self._last_tap_time[hovered_key] = timestamp
                        return hovered_key  # Return the key action
                else:
                    self._phase = self.TapPhase.HOVERING

        return None

    def reset(self):
        self._phase = self.TapPhase.IDLE
        self._peak_y = None
        self._start_y = None
        self._hover_count = 0
        self._hovered_key = None


# ─── Virtual Keyboard Engine ─────────────────────────────────────────────────

class VirtualKeyboard:
    """
    Manages virtual keyboard state and key targeting.
    
    Takes normalized index fingertip position and determines:
    1. Which key is currently hovered
    2. Whether an air tap has occurred
    3. What text/action to output
    
    The actual rendering is done by the Electron overlay UI.
    """

    def __init__(self):
        self._layout = build_keyboard_layout()
        self._tap_detector = AirTapDetector()
        self._shift_active = False
        self._caps_lock = False
        self._hovered_key: Optional[KeyLayout] = None
        self._typed_chars: List[str] = []
        self._active = False

    def activate(self):
        """Activate keyboard mode."""
        self._active = True
        self._tap_detector.reset()
        logger.info("Virtual keyboard activated")

    def deactivate(self):
        """Deactivate keyboard mode."""
        self._active = False
        self._hovered_key = None
        self._tap_detector.reset()
        logger.info("Virtual keyboard deactivated")

    def update(
        self,
        norm_x: float,
        norm_y: float,
        timestamp: float,
    ) -> Optional[str]:
        """
        Update keyboard with current fingertip position.
        Returns action string if a key is activated, else None.
        
        Actions: single char (e.g. "a"), "space", "backspace", "enter", "shift"
        """
        if not self._active:
            return None

        # Find hovered key
        self._hovered_key = self._find_hovered_key(norm_x, norm_y)
        hovered_action = self._hovered_key.action if self._hovered_key else None

        # Check for air tap
        activated = self._tap_detector.update(norm_y, hovered_action, timestamp)

        if activated is None:
            return None

        return self._process_key(activated)

    def _find_hovered_key(self, norm_x: float, norm_y: float) -> Optional[KeyLayout]:
        """Find which key the fingertip is over."""
        for key in self._layout:
            if (abs(norm_x - key.norm_x) <= key.width / 2 and
                    abs(norm_y - key.norm_y) <= key.height / 2):
                return key
        return None

    def _process_key(self, action: str) -> str:
        """Process key action, handling shift/caps."""
        if action == "shift":
            self._shift_active = not self._shift_active
            return "shift"
        elif action == "space":
            self._shift_active = False
            return "space"
        elif action == "backspace":
            if self._typed_chars:
                self._typed_chars.pop()
            return "backspace"
        elif action == "enter":
            return "enter"
        else:
            # Regular character
            char = action
            if self._shift_active or self._caps_lock:
                char = char.upper()
            else:
                char = char.lower()
            self._shift_active = False  # Auto-release shift
            self._typed_chars.append(char)
            return char

    def get_state(self) -> dict:
        """State dict for sending to UI."""
        return {
            "active": self._active,
            "hovered_key": self._hovered_key.label if self._hovered_key else None,
            "shift_active": self._shift_active,
            "typed_text": "".join(self._typed_chars),
            "layout": [
                {
                    "label": k.label,
                    "x": k.norm_x,
                    "y": k.norm_y,
                    "w": k.width,
                    "h": k.height,
                    "action": k.action,
                }
                for k in self._layout
            ],
        }

    def clear_typed(self):
        """Clear the typed text buffer."""
        self._typed_chars = []
