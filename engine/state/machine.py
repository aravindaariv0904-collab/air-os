"""
AirOS Engine — Interaction State Machine
Manages state transitions and dispatches actions based on current state + gesture.

Key rules:
- While DRAG is active, vertical movement must NOT trigger SCROLL.
- While KEYBOARD is active, swipes must NOT navigate.
- Custom gestures cannot override PAUSED → OFF transitions.
- State transitions are logged for debugging.
"""

import time
import logging
from typing import Optional, Callable

from engine.state.states import InteractionState, GestureType
from engine.gestures.recognizer import GestureEvent

logger = logging.getLogger(__name__)


class StateMachine:
    """
    Manages the AirOS interaction state.
    
    Receives gesture events and returns the appropriate action to execute.
    Actions are returned as strings from a predefined action vocabulary.
    
    Usage:
        sm = StateMachine()
        sm.on_state_change = my_callback
        action = sm.process(gesture_event, context)
    """

    def __init__(self):
        self._state = InteractionState.IDLE
        self._prev_state = InteractionState.IDLE
        self._state_entered: float = time.monotonic()
        self._pinch_was_dragging = False
        self.on_state_change: Optional[Callable[[InteractionState, InteractionState], None]] = None

    @property
    def state(self) -> InteractionState:
        return self._state

    @property
    def state_name(self) -> str:
        return self._state.name

    def process(
        self,
        gesture: GestureType,
        is_pinched: bool,
        is_pinch_approaching: bool,
        num_hands: int,
        has_index_pointer: bool,
        speed: float,
        gesture_event: Optional[GestureEvent] = None,
    ) -> list[str]:
        """
        Process current gesture state and return list of actions to execute.
        
        Actions are strings like: "cursor_move", "left_click", "scroll_up", etc.
        The action executor in main.py maps these to actual SendInput calls.
        
        Returns an empty list if no action should be taken.
        """
        actions = []

        # ═══════════════════════════════════════════════════════════════
        # GLOBAL transitions — always available regardless of state
        # ═══════════════════════════════════════════════════════════════

        # PAUSE: Open palm gesture always available (safety mechanism)
        if gesture == GestureType.OPEN_PALM and self._state not in (
            InteractionState.PAUSED, InteractionState.OFF, InteractionState.CALIBRATION
        ):
            self._transition(InteractionState.PAUSED)
            return ["pause"]

        # RESUME from PAUSED: closed fist or lowered hand
        if self._state == InteractionState.PAUSED:
            if gesture != GestureType.OPEN_PALM and num_hands > 0:
                # If we've been paused for at least 0.5s, allow resumption
                if time.monotonic() - self._state_entered > 0.5:
                    self._transition(InteractionState.POINTER if has_index_pointer else InteractionState.IDLE)
                    return ["resume"]
            return []  # No actions while PAUSED

        # OFF state — no actions
        if self._state == InteractionState.OFF:
            return []

        # ═══════════════════════════════════════════════════════════════
        # No hands detected → IDLE
        # ═══════════════════════════════════════════════════════════════
        if num_hands == 0:
            if self._state not in (InteractionState.IDLE,):
                # Clean up drag state if tracking is lost
                if self._state == InteractionState.DRAG:
                    actions.append("mouse_up")
                    self._pinch_was_dragging = False
                self._transition(InteractionState.IDLE)
            return actions

        # ═══════════════════════════════════════════════════════════════
        # TWO HANDS → Keyboard mode entry
        # ═══════════════════════════════════════════════════════════════
        if gesture == GestureType.TWO_HANDS and self._state not in (
            InteractionState.KEYBOARD, InteractionState.CALIBRATION
        ):
            self._transition(InteractionState.KEYBOARD)
            return ["enter_keyboard"]

        # Exit keyboard if only one hand
        if self._state == InteractionState.KEYBOARD and num_hands < 2:
            if time.monotonic() - self._state_entered > 0.5:  # Grace period
                self._transition(InteractionState.POINTER if has_index_pointer else InteractionState.IDLE)
                return ["exit_keyboard"]
            return []

        if self._state == InteractionState.KEYBOARD:
            # Keyboard mode: only keyboard-specific actions are generated
            # (handled by keyboard module separately)
            return []

        # ═══════════════════════════════════════════════════════════════
        # PINCH / DRAG state
        # ═══════════════════════════════════════════════════════════════
        now = time.monotonic()

        if self._state == InteractionState.DRAG:
            if is_pinched:
                actions.append("cursor_move")  # Continue drag — cursor tracks finger
            else:
                # Pinch released — end drag
                actions.append("mouse_up")
                self._pinch_was_dragging = False
                self._pinch_start_time = None
                self._transition(InteractionState.POINTER)
            return actions

        if self._state == InteractionState.CLICK:
            # Brief click state — transition back to POINTER
            self._transition(InteractionState.POINTER)

        # ═══════════════════════════════════════════════════════════════
        # POINTER state — main interaction state
        # ═══════════════════════════════════════════════════════════════
        if self._state in (InteractionState.IDLE, InteractionState.POINTER):
            # Transition to POINTER when hand is visible (with or without index pointer)
            if self._state != InteractionState.POINTER:
                self._transition(InteractionState.POINTER)

            # Cursor tracks index fingertip when index is extended
            if has_index_pointer:
                actions.append("cursor_move")

            # Pinch → drag start (allowed from any hand pose, not just index-only)
            # Geometrically: when pinching, the index tip touches thumb → is_index_only is False.
            # We must allow drag entry from pinch regardless of pointer state.
            if is_pinched:
                if not self._pinch_was_dragging:
                    # First frame of pinch — move cursor to current pos then start drag
                    if "cursor_move" not in actions:
                        actions.append("cursor_move")
                    actions.append("mouse_down")
                    self._pinch_was_dragging = True
                    self._transition(InteractionState.DRAG)
                return actions
            else:
                self._pinch_was_dragging = False

        # ═══════════════════════════════════════════════════════════════
        # SCROLL
        # ═══════════════════════════════════════════════════════════════
        if self._state == InteractionState.POINTER:
            if gesture == GestureType.SCROLL_UP:
                self._transition(InteractionState.SCROLL)
                return ["scroll_up"]
            if gesture == GestureType.SCROLL_DOWN:
                self._transition(InteractionState.SCROLL)
                return ["scroll_down"]

        if self._state == InteractionState.SCROLL:
            # Continue scrolling or return to pointer
            if gesture in (GestureType.SCROLL_UP, GestureType.SCROLL_DOWN):
                return [gesture.name.lower()]
            else:
                self._transition(InteractionState.POINTER)
                return []

        # ═══════════════════════════════════════════════════════════════
        # SWIPE / NAVIGATION
        # ═══════════════════════════════════════════════════════════════
        if self._state == InteractionState.POINTER:
            if gesture == GestureType.SWIPE_LEFT:
                self._transition(InteractionState.NAVIGATION)
                return ["navigate_back"]
            if gesture == GestureType.SWIPE_RIGHT:
                self._transition(InteractionState.NAVIGATION)
                return ["navigate_forward"]

        if self._state == InteractionState.NAVIGATION:
            # Navigation is brief — return to pointer
            if time.monotonic() - self._state_entered > 0.3:
                self._transition(InteractionState.POINTER)
            return []

        return actions

    def force_state(self, state: InteractionState):
        """Force a state transition (used by calibration, settings, etc.)."""
        self._transition(state)

    def _transition(self, new_state: InteractionState):
        """Perform a state transition with logging."""
        if new_state == self._state:
            return
        self._prev_state = self._state
        self._state = new_state
        self._state_entered = time.monotonic()
        logger.debug(f"State: {self._prev_state.name} -> {new_state.name}")
        if self.on_state_change:
            try:
                self.on_state_change(self._prev_state, new_state)
            except Exception as e:
                logger.error(f"State change callback error: {e}")

    def stop(self):
        """Stop the engine safely."""
        self._transition(InteractionState.OFF)

    def get_state_duration(self) -> float:
        """Seconds spent in current state."""
        return time.monotonic() - self._state_entered
