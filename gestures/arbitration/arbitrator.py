"""
AirOS Engine — Central Gesture Arbitrator
Arbitrates system and custom gesture candidates by strict priority to prevent ambiguity.

Priority Hierarchy:
1. Emergency Stop (Hotkey Ctrl+Alt+A)
2. Open Palm (Pause AirOS)
3. Calibration Mode
4. Keyboard Mode (Two Hands)
5. Pinch / Drag
6. Click
7. Navigation (Swipe)
8. Scroll
9. Pointer (Index Finger)
10. Custom Gestures (Gesture Studio)
"""

import logging
from typing import Optional, Tuple
from engine.state.states import GestureType
from engine.gestures.recognizer import GestureEvent

logger = logging.getLogger(__name__)


class GestureArbitrator:
    """
    Central arbitrator enforcing gesture priority rules.
    """

    def arbitrate(
        self,
        system_event: Optional[GestureEvent],
        custom_gesture_id: Optional[str],
        is_pinched: bool,
        is_paused: bool,
        is_calibrating: bool,
        is_keyboard: bool,
    ) -> Tuple[Optional[GestureEvent], Optional[str]]:
        """
        Evaluates candidate gestures and returns (winning_system_event, winning_custom_id).
        """
        # 1. Open Palm (Pause) safety always overrides normal gestures
        if system_event and system_event.gesture == GestureType.OPEN_PALM:
            return system_event, None

        if is_paused or is_calibrating:
            return None, None

        # 2. Two Hands (Keyboard entry) overrides single hand movement
        if system_event and system_event.gesture == GestureType.TWO_HANDS:
            return system_event, None

        # 3. In Keyboard mode: disable swipe, scroll, navigation, custom gestures
        if is_keyboard:
            return None, None

        # 4. Active pinch / drag overrides scroll, swipe, and custom gestures
        if is_pinched:
            return None, None

        # 5. System gestures (Scroll, Swipe) override custom gestures
        if system_event is not None:
            return system_event, None

        # 6. Custom gestures fire if no system gesture candidate is present
        if custom_gesture_id is not None:
            return None, custom_gesture_id

        return None, None
