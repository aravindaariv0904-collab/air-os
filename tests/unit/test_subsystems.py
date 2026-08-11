"""
AirOS — Tests for keyboard, calibration, scroll, swipe, safety, and conflicts.
These tests run without a webcam or MediaPipe model (synthetic landmarks only).
"""

import sys
import os
import time
import math
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Scroll Detector
# =============================================================================

class TestScrollDetector:
    def _scroll_test(self, velocity_y, frames):
        """Feed N frames at a given vertical velocity. Returns events fired."""
        from engine.gestures.recognizer import ScrollDetector
        from engine.state.states import GestureType
        det = ScrollDetector()
        events = []
        t = time.monotonic()
        for _ in range(frames):
            ev = det.update(velocity_y, t)
            if ev:
                events.append(ev.gesture)
            t += 1 / 30.0
        return events

    def test_slow_down_movement_scrolls(self):
        from engine.state.states import GestureType
        # velocity_y > threshold → moving down → scroll_down
        events = self._scroll_test(0.5, 10)
        assert GestureType.SCROLL_DOWN in events

    def test_fast_up_movement_scrolls_up(self):
        from engine.state.states import GestureType
        events = self._scroll_test(-0.5, 10)
        assert GestureType.SCROLL_UP in events

    def test_no_scroll_below_threshold(self):
        # Small movement must NOT scroll
        events = self._scroll_test(0.02, 30)
        assert events == []

    def test_rate_limited(self):
        """Scroll events should be rate-limited (cooldown)."""
        from engine.gestures.recognizer import ScrollDetector
        from engine.state.states import GestureType
        det = ScrollDetector()
        t = time.monotonic()
        count = 0
        for _ in range(60):  # 2 seconds at 30fps
            ev = det.update(0.8, t)
            if ev:
                count += 1
            t += 1 / 30.0
        # With cooldown of 0.08s, should fire several times but not 60
        assert 5 < count < 60


# =============================================================================
# Swipe Detector
# =============================================================================

class TestSwipeDetector:
    def _swipe_test(self, dx, dy, vx, frames):
        from engine.gestures.recognizer import SwipeDetector
        det = SwipeDetector()
        events = []
        t = time.monotonic()
        for _ in range(frames):
            ev = det.update(dx, dy, vx, t)
            if ev:
                events.append(ev.gesture)
            t += 1 / 30.0
        return events

    def test_right_swipe_detected(self):
        from engine.state.states import GestureType
        events = self._swipe_test(0.3, 0.01, 0.6, 10)
        assert GestureType.SWIPE_RIGHT in events

    def test_left_swipe_detected(self):
        from engine.state.states import GestureType
        events = self._swipe_test(-0.3, 0.01, -0.6, 10)
        assert GestureType.SWIPE_LEFT in events

    def test_diagonal_movement_rejected(self):
        """Diagonal movement (similar dx and dy) must NOT be a swipe."""
        events = self._swipe_test(0.3, 0.25, 0.6, 10)
        assert events == []

    def test_small_displacement_rejected(self):
        events = self._swipe_test(0.05, 0.01, 0.1, 10)
        assert events == []


# =============================================================================
# Virtual Keyboard / Air Tap
# =============================================================================

class TestVirtualKeyboard:
    def test_layout_has_expected_keys(self):
        from keyboard.air_tap.tap_detector import build_keyboard_layout
        layout = build_keyboard_layout()
        labels = [k.label for k in layout]
        assert len(layout) > 30
        for expected in ("Q", "W", "E", "A", "Z", "SPACE", "ENTER", "SHIFT", "⌫"):
            assert expected in labels, f"Missing key {expected}"

    def test_keys_are_non_overlapping(self):
        """Key hit areas must not overlap (targeting integrity)."""
        from keyboard.air_tap.tap_detector import build_keyboard_layout
        layout = build_keyboard_layout()
        for i, a in enumerate(layout):
            for j, b in enumerate(layout):
                if i >= j:
                    continue
                x_overlap = abs(a.norm_x - b.norm_x) < (a.width + b.width) / 2
                y_overlap = abs(a.norm_y - b.norm_y) < (a.height + b.height) / 2
                assert not (x_overlap and y_overlap), f"Keys overlap: {a.label} vs {b.label}"

    def test_hover_highlights_nearest_key(self):
        from keyboard.air_tap.tap_detector import VirtualKeyboard
        kb = VirtualKeyboard()
        kb.activate()
        # Point at roughly the 'H' key area (middle of row 3)
        hovered = kb._find_hovered_key(0.55, 0.70)
        assert hovered is not None

    def test_air_tap_requires_motion_not_hover(self):
        """Hovering without motion must NOT activate a key."""
        from keyboard.air_tap.tap_detector import AirTapDetector
        det = AirTapDetector()
        t = time.monotonic()
        # Hover over 'a' with no Y movement for 30 frames
        result = None
        for _ in range(30):
            result = det.update(0.65, "a", t)
            t += 1 / 30.0
        assert result is None, "Hovering alone triggered a key"

    def test_air_tap_fires_on_tap_cycle(self):
        """A deliberate down-up Y cycle should fire the key once."""
        from keyboard.air_tap.tap_detector import AirTapDetector
        det = AirTapDetector()
        t = time.monotonic()
        activations = []
        # Hover
        for _ in range(5):
            det.update(0.60, "a", t)
            t += 1 / 30.0
        # Down stroke (Y increases downward)
        for _ in range(6):
            r = det.update(0.60 + _ * 0.01, "a", t)
            if r:
                activations.append(r)
            t += 1 / 30.0
        # Return stroke (Y decreases)
        for _ in range(8):
            r = det.update(0.66 - _ * 0.01, "a", t)
            if r:
                activations.append(r)
            t += 1 / 30.0
        assert "a" in activations, f"Expected 'a' tap, got {activations}"

    def test_air_tap_debounced(self):
        """One tap motion must not produce repeated activations."""
        from keyboard.air_tap.tap_detector import AirTapDetector
        det = AirTapDetector()
        t = time.monotonic()
        activations = []

        def do_tap():
            nonlocal t
            for _ in range(5):
                det.update(0.60, "a", t)
                t += 1 / 30.0
            for i in range(6):
                r = det.update(0.60 + i * 0.01, "a", t)
                if r:
                    activations.append(r)
                t += 1 / 30.0
            for i in range(8):
                r = det.update(0.66 - i * 0.01, "a", t)
                if r:
                    activations.append(r)
                t += 1 / 30.0

        do_tap()
        # Immediately repeat (within debounce window)
        do_tap()
        assert len(activations) <= 1, f"Debounce failed: {len(activations)} activations"

    def test_shift_uppercases(self):
        from keyboard.air_tap.tap_detector import VirtualKeyboard
        kb = VirtualKeyboard()
        kb.activate()
        # Press shift then 'a'
        assert kb._process_key("shift") == "shift"
        char = kb._process_key("a")
        assert char == "A", f"Expected 'A', got {char}"


# =============================================================================
# Calibration
# =============================================================================

class FakeClock:
    """Deterministic monotonic clock for calibration tests."""
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        self.now += 1 / 30.0
        return self.now


class TestCalibration:
    def test_default_profile_sane(self):
        from engine.calibration.calibrator import CalibrationManager, CalibrationProfile
        cal = CalibrationManager()
        assert isinstance(cal.profile, CalibrationProfile)
        p = cal.profile
        assert 0 < p.region_left < p.region_right < 1
        assert 0 < p.region_top < p.region_bottom < 1
        assert p.pinch_threshold > 0

    def test_profile_roundtrip(self):
        """Profile to_dict/from_dict round-trip should preserve fields."""
        from engine.calibration.calibrator import CalibrationProfile
        p = CalibrationProfile(region_left=0.2, region_right=0.8, sensitivity=1.5)
        d = p.to_dict()
        p2 = CalibrationProfile.from_dict(d)
        assert p2.region_left == 0.2
        assert p2.sensitivity == 1.5

    def test_calibration_starts_at_check_camera(self):
        from engine.calibration.calibrator import CalibrationManager, CalibStep
        cal = CalibrationManager(clock=FakeClock())
        cal.start()
        assert cal.current_step == CalibStep.CHECK_CAMERA

    def test_calibration_flow_to_complete(self):
        """Feed synthetic samples through the workflow until complete."""
        from engine.calibration.calibrator import CalibrationManager, CalibStep
        import engine.calibration.calibrator as calib_mod
        import tempfile, os
        # Isolate from real AppData
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            tmp_path = tf.name
        original = calib_mod.CALIBRATION_FILE
        calib_mod.CALIBRATION_FILE = tmp_path
        try:
            cal = CalibrationManager(clock=FakeClock())
            cal.start()
            lm = np.zeros((21, 3), dtype=np.float32)
            lm[0] = [0.5, 0.5, 0.0]
            done = False
            for _ in range(6000):
                done = cal.update(lm, num_hands=1, wrist_pos=[0.5, 0.5], pinch_dist=0.2)
                if done:
                    break
            assert cal.current_step == CalibStep.COMPLETE or cal.profile.calibrated, \
                f"Calibration did not complete. Step={cal.current_step}"
        finally:
            calib_mod.CALIBRATION_FILE = original
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# =============================================================================
# Safety: PAUSED / OFF blocking
# =============================================================================

class TestSafety:
    def test_paused_blocks_all_actions(self):
        from engine.state.machine import StateMachine
        from engine.state.states import InteractionState, GestureType
        sm = StateMachine()
        sm.force_state(InteractionState.PAUSED)
        for gesture in (
            GestureType.INDEX_POINTER, GestureType.PINCH, GestureType.SCROLL_UP,
            GestureType.SCROLL_DOWN, GestureType.SWIPE_LEFT, GestureType.SWIPE_RIGHT,
        ):
            actions = sm.process(gesture, False, False, 1, True, 0.5)
            assert actions == [], f"PAUSED allowed action for {gesture.name}: {actions}"

    def test_off_blocks_all_actions(self):
        from engine.state.machine import StateMachine
        from engine.state.states import InteractionState, GestureType
        sm = StateMachine()
        sm.force_state(InteractionState.OFF)
        actions = sm.process(GestureType.INDEX_POINTER, False, False, 1, True, 0.5)
        assert actions == []

    def test_open_palm_pauses_from_any_state(self):
        from engine.state.machine import StateMachine
        from engine.state.states import InteractionState, GestureType
        sm = StateMachine()
        sm.process(GestureType.INDEX_POINTER, False, False, 1, True, 0.0)
        sm.process(GestureType.PINCH, True, False, 1, True, 0.0)  # → DRAG
        actions = sm.process(GestureType.OPEN_PALM, False, False, 1, False, 0.0)
        assert sm.state == InteractionState.PAUSED
        assert "pause" in actions

    def test_drag_does_not_trigger_scroll(self):
        """While DRAG active, vertical movement must not produce scroll actions."""
        from engine.state.machine import StateMachine
        from engine.state.states import InteractionState, GestureType
        sm = StateMachine()
        sm.process(GestureType.INDEX_POINTER, False, False, 1, True, 0.0)
        sm.process(GestureType.PINCH, True, False, 1, True, 0.0)  # → DRAG
        actions = sm.process(GestureType.SCROLL_UP, True, False, 1, True, 0.3)
        assert "scroll_up" not in actions
        assert "cursor_move" in actions  # continues drag tracking

    def test_keyboard_mode_blocks_navigation(self):
        """In KEYBOARD mode, swipes must not navigate the browser."""
        from engine.state.machine import StateMachine
        from engine.state.states import InteractionState, GestureType
        sm = StateMachine()
        sm.process(GestureType.TWO_HANDS, False, False, 2, True, 0.0)  # → KEYBOARD
        assert sm.state == InteractionState.KEYBOARD
        actions = sm.process(GestureType.SWIPE_LEFT, False, False, 2, True, 0.0)
        assert "navigate_back" not in actions


# =============================================================================
# Gesture Conflict Detection (custom vs system)
# =============================================================================

class TestGestureConflicts:
    def test_registry_has_no_duplicate_ids(self):
        from gestures.registry.manager import GestureRegistry
        registry = GestureRegistry()
        registry.load()
        ids = [g.id for g in registry.get_all()]
        assert len(ids) == len(set(ids)), "Duplicate gesture IDs in registry"

    def test_system_gestures_immutable(self):
        """System gestures must always be present regardless of profiles."""
        from gestures.registry.manager import GestureRegistry
        registry = GestureRegistry()
        registry.load()
        system_ids = {g.id for g in registry.get_all() if g.system}
        for expected in ("index_pointer", "pinch_click", "scroll_up", "swipe_left",
                         "open_palm", "two_hands"):
            assert expected in system_ids, f"Missing system gesture {expected}"

    def test_custom_gesture_action_must_be_valid(self):
        """Custom gesture actions must exist in the action registry."""
        from input.windows.send_input import WindowsInputAdapter
        from input.action_registry import ActionRegistry
        from gestures.registry.manager import GestureRegistry
        adapter = WindowsInputAdapter()
        adapter.disable()
        reg = ActionRegistry(adapter)
        registry = GestureRegistry()
        registry.load()
        for g in registry.get_all():
            if g.action in ("cursor_move", "drag", "mouse_down", "mouse_up",
                            "pause", "resume", "enter_keyboard", "exit_keyboard"):
                continue  # engine-handled
            assert reg.is_valid_action(g.action), \
                f"Gesture {g.id} maps to invalid action {g.action}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
