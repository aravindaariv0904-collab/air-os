"""
AirOS Engine — Interaction State Machine
Defines all possible states and transitions for the gesture interaction system.
"""

from enum import Enum, auto


class InteractionState(Enum):
    """
    All possible states of the AirOS interaction state machine.
    
    Transitions follow strict rules — see machine.py for the full graph.
    """
    IDLE = auto()           # No hand detected or engine not tracking
    POINTER = auto()        # Index finger extended — cursor movement mode
    CLICK = auto()          # Pinch confirmed — click action triggered
    DRAG = auto()           # Pinch held + movement — drag mode
    SCROLL = auto()         # Vertical hand movement — scroll mode
    NAVIGATION = auto()     # Swipe in progress — navigation action
    TWO_HAND = auto()       # Two hands detected — about to enter keyboard
    KEYBOARD = auto()       # Virtual keyboard mode active
    PAUSED = auto()         # Open palm held — gesture input suspended
    CALIBRATION = auto()    # Calibration workflow in progress
    OFF = auto()            # Engine fully stopped

    def __str__(self):
        return self.name


class GestureType(Enum):
    """Recognized gesture types."""
    NONE = auto()
    INDEX_POINTER = auto()      # ☝️ Single index finger up
    PINCH = auto()              # 🤏 Index + thumb close
    PINCH_DRAG = auto()         # 🤏 Pinch + movement
    SCROLL_UP = auto()          # ↑ Hand moving up
    SCROLL_DOWN = auto()        # ↓ Hand moving down
    SWIPE_LEFT = auto()         # ← Horizontal left movement
    SWIPE_RIGHT = auto()        # → Horizontal right movement
    OPEN_PALM = auto()          # 🖐️ All fingers extended
    TWO_HANDS = auto()          # 👐 Both hands detected
    FIST = auto()               # Closed fist
    POINTING_UP = auto()        # Index pointing up (alternative to INDEX_POINTER)

    def __str__(self):
        return self.name


# Human-readable gesture descriptions for UI display
GESTURE_DESCRIPTIONS = {
    GestureType.NONE: ("", "No gesture"),
    GestureType.INDEX_POINTER: ("[1]", "Pointer -- move cursor"),
    GestureType.PINCH: ("[P]", "Pinch -- left click"),
    GestureType.PINCH_DRAG: ("[P]", "Pinch drag -- drag"),
    GestureType.SCROLL_UP: ("[^]", "Hand up -- scroll up"),
    GestureType.SCROLL_DOWN: ("[v]", "Hand down -- scroll down"),
    GestureType.SWIPE_LEFT: ("[<]", "Swipe left -- back"),
    GestureType.SWIPE_RIGHT: ("[>]", "Swipe right -- forward"),
    GestureType.OPEN_PALM: ("[*]", "Open palm -- pause"),
    GestureType.TWO_HANDS: ("[2]", "Two hands -- keyboard"),
    GestureType.FIST: ("[F]", "Fist"),
    GestureType.POINTING_UP: ("[1]", "Pointing up"),
}
