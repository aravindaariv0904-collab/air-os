"""
Unit tests for AirOS core modules.
These tests run without a webcam or MediaPipe model.
They test the mathematical algorithms and state logic.
"""

import sys
import os
import time
import math
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# One Euro Filter Tests
# =============================================================================

class TestOneEuroFilter:
    def test_stable_signal_low_noise(self):
        """Filter should stabilize a noisy static signal."""
        from engine.filtering.one_euro import OneEuroFilter
        f = OneEuroFilter(freq=30.0, min_cutoff=1.0, beta=0.007)
        # Apply 30 frames of noisy signal around 0.5
        outputs = []
        for _ in range(30):
            val = 0.5 + (np.random.random() - 0.5) * 0.02
            outputs.append(f(val))
        # After warmup, output should be close to 0.5
        assert abs(outputs[-1] - 0.5) < 0.05, f"Filter not stable: {outputs[-1]}"

    def test_follows_fast_movement(self):
        """Filter must track fast movement — should adapt with high beta."""
        from engine.filtering.one_euro import OneEuroFilter
        # High beta = more responsive to velocity
        f = OneEuroFilter(freq=30.0, min_cutoff=0.5, beta=0.1)
        ts = 0.0
        dt = 1/30.0
        # Stabilize at 0.1
        for _ in range(30):
            f(0.1, ts)
            ts += dt
        # Now jump to 0.9 — give it 10 frames to adapt
        result = 0.1
        for _ in range(10):
            result = f(0.9, ts)
            ts += dt
        # After 10 frames with high beta, should be well above 0.4
        assert result > 0.4, f"Filter too slow for fast movement: {result}"

    def test_2d_filter(self):
        """2D filter should work independently on X and Y."""
        from engine.filtering.one_euro import OneEuroFilter2D
        f = OneEuroFilter2D()
        x, y = f(0.5, 0.3)
        assert isinstance(x, float)
        assert isinstance(y, float)

    def test_reset_clears_state(self):
        """Reset should allow filter to start fresh."""
        from engine.filtering.one_euro import OneEuroFilter
        f = OneEuroFilter()
        for _ in range(10):
            f(0.5)
        f.reset()
        # After reset, first value should pass through
        result = f(0.9)
        assert abs(result - 0.9) < 0.01


# =============================================================================
# Geometry Tests
# =============================================================================

class TestGeometry:
    def _make_landmarks(self):
        """Create a realistic hand landmark array (21 points)."""
        # All zeros except key points
        lm = np.zeros((21, 3), dtype=np.float32)
        # Wrist at bottom center
        lm[0] = [0.5, 0.8, 0.0]
        # Thumb
        lm[1] = [0.35, 0.75, 0.0]
        lm[2] = [0.25, 0.70, 0.0]
        lm[3] = [0.20, 0.65, 0.0]
        lm[4] = [0.15, 0.60, 0.0]  # Thumb tip
        # Index finger
        lm[5] = [0.45, 0.65, 0.0]  # MCP
        lm[6] = [0.43, 0.55, 0.0]
        lm[7] = [0.42, 0.45, 0.0]
        lm[8] = [0.41, 0.35, 0.0]  # Index tip (extended)
        # Middle finger
        lm[9]  = [0.50, 0.63, 0.0]
        lm[10] = [0.50, 0.55, 0.0]
        lm[11] = [0.50, 0.50, 0.0]
        lm[12] = [0.50, 0.70, 0.0]  # Middle tip (curled - below MCP)
        # Ring finger
        lm[13] = [0.55, 0.65, 0.0]
        lm[14] = [0.55, 0.55, 0.0]
        lm[15] = [0.55, 0.50, 0.0]
        lm[16] = [0.55, 0.70, 0.0]  # Ring tip (curled)
        # Pinky
        lm[17] = [0.60, 0.68, 0.0]
        lm[18] = [0.62, 0.60, 0.0]
        lm[19] = [0.63, 0.55, 0.0]
        lm[20] = [0.63, 0.72, 0.0]  # Pinky tip (curled)
        return lm

    def test_hand_scale_nonzero(self):
        """Hand scale should be nonzero for valid landmarks."""
        from engine.landmarks.geometry import hand_scale
        lm = self._make_landmarks()
        scale = hand_scale(lm)
        assert scale > 0.01

    def test_pinch_distance_far(self):
        """When index and thumb are far apart, distance should be > 0.3."""
        from engine.landmarks.geometry import normalized_pinch_distance
        lm = self._make_landmarks()
        # Thumb tip at [0.15, 0.60], index tip at [0.41, 0.35]
        dist = normalized_pinch_distance(lm)
        assert dist > 0.3, f"Expected distance > 0.3, got {dist:.3f}"

    def test_pinch_distance_close(self):
        """When index and thumb are close, distance should be < 0.3."""
        from engine.landmarks.geometry import normalized_pinch_distance
        lm = self._make_landmarks()
        # Move index tip to same location as thumb tip
        lm[8] = [0.15, 0.62, 0.0]  # Near thumb tip
        dist = normalized_pinch_distance(lm)
        assert dist < 0.3, f"Expected distance < 0.3, got {dist:.3f}"

    def test_index_pointer_detection(self):
        """Index only extended should be detected."""
        from engine.landmarks.geometry import is_index_only
        lm = self._make_landmarks()
        # Index extended (tip above MCP), others curled (tip below MCP)
        assert is_index_only(lm), "Index only not detected"

    def test_open_palm_with_all_extended(self):
        """Open palm requires all fingers extended."""
        from engine.landmarks.geometry import is_open_palm
        lm = self._make_landmarks()
        # All fingers curled — not open palm
        assert not is_open_palm(lm)
        # Extend all fingers
        lm[12] = [0.50, 0.40, 0.0]  # Middle above MCP
        lm[16] = [0.55, 0.42, 0.0]  # Ring above MCP
        lm[20] = [0.63, 0.45, 0.0]  # Pinky above MCP
        assert is_open_palm(lm), "Open palm not detected"


# =============================================================================
# Motion Estimator Tests
# =============================================================================

class TestMotionEstimator:
    def test_velocity_computation(self):
        """Velocity should be computed from position differences."""
        from engine.motion.estimator import MotionEstimator
        est = MotionEstimator()
        t = 0.0
        est.update(0.1, 0.5, t)
        t += 1/30.0
        state = est.update(0.4, 0.5, t)  # Moving right at 0.3/frame * 30fps = 9 units/s
        assert state.velocity[0] > 0, "Should have positive X velocity"
        assert state.is_moving_right, "Should be moving right"

    def test_reset_clears_history(self):
        """Reset should clear all history."""
        from engine.motion.estimator import MotionEstimator
        est = MotionEstimator()
        for i in range(10):
            est.update(float(i) * 0.1, 0.5, float(i) * 0.033)
        est.reset()
        assert len(est._history) == 0

    def test_displacement_short_window(self):
        """Short displacement should capture recent movement."""
        from engine.motion.estimator import MotionEstimator
        est = MotionEstimator()
        t = 0.0
        # Move steadily to the right
        for i in range(20):
            est.update(0.1 + i * 0.02, 0.5, t)
            t += 1/30.0
        state = est.get_state()
        # Should have positive X displacement in short window
        assert state.displacement_short[0] > 0, "Should have positive displacement"


# =============================================================================
# State Machine Tests
# =============================================================================

class TestStateMachine:
    def test_initial_state_is_idle(self):
        """State machine starts in IDLE."""
        from engine.state.machine import StateMachine
        from engine.state.states import InteractionState
        sm = StateMachine()
        assert sm.state == InteractionState.IDLE

    def test_no_hands_returns_idle(self):
        """No hands should result in IDLE state."""
        from engine.state.machine import StateMachine
        from engine.state.states import InteractionState, GestureType
        sm = StateMachine()
        sm.process(GestureType.NONE, False, False, 0, False, 0.0)
        assert sm.state == InteractionState.IDLE

    def test_index_pointer_enters_pointer_state(self):
        """Index pointer gesture should enter POINTER state."""
        from engine.state.machine import StateMachine
        from engine.state.states import InteractionState, GestureType
        sm = StateMachine()
        actions = sm.process(GestureType.INDEX_POINTER, False, False, 1, True, 0.05)
        assert sm.state == InteractionState.POINTER
        assert "cursor_move" in actions

    def test_pinch_during_pointer_enters_drag(self):
        """Pinch while in POINTER state should start drag."""
        from engine.state.machine import StateMachine
        from engine.state.states import InteractionState, GestureType
        sm = StateMachine()
        # First enter pointer
        sm.process(GestureType.INDEX_POINTER, False, False, 1, True, 0.0)
        # Now pinch
        actions = sm.process(GestureType.PINCH, True, False, 1, True, 0.0)
        assert sm.state == InteractionState.DRAG
        assert "mouse_down" in actions

    def test_open_palm_triggers_pause(self):
        """Open palm should always trigger PAUSE."""
        from engine.state.machine import StateMachine
        from engine.state.states import InteractionState, GestureType
        sm = StateMachine()
        # From pointer state
        sm.process(GestureType.INDEX_POINTER, False, False, 1, True, 0.0)
        actions = sm.process(GestureType.OPEN_PALM, False, False, 1, False, 0.0)
        assert sm.state == InteractionState.PAUSED
        assert "pause" in actions

    def test_no_actions_when_paused(self):
        """PAUSED state should generate no cursor or scroll actions."""
        from engine.state.machine import StateMachine
        from engine.state.states import InteractionState, GestureType
        sm = StateMachine()
        sm.force_state(InteractionState.PAUSED)
        # Try various gestures
        actions = sm.process(GestureType.SCROLL_UP, False, False, 1, True, 0.3)
        assert "scroll_up" not in actions
        actions = sm.process(GestureType.INDEX_POINTER, False, False, 1, True, 0.3)
        assert "cursor_move" not in actions


# =============================================================================
# Pinch Detector Tests
# =============================================================================

class TestPinchDetector:
    def _make_landmarks_far(self):
        lm = np.zeros((21, 3), dtype=np.float32)
        lm[0] = [0.5, 0.8, 0.0]
        lm[5] = [0.45, 0.65, 0.0]
        lm[9] = [0.50, 0.63, 0.0]
        lm[4] = [0.15, 0.60, 0.0]  # Thumb far
        lm[8] = [0.45, 0.30, 0.0]  # Index far
        return lm

    def _make_landmarks_close(self):
        lm = np.zeros((21, 3), dtype=np.float32)
        lm[0] = [0.5, 0.8, 0.0]
        lm[5] = [0.45, 0.65, 0.0]
        lm[9] = [0.50, 0.63, 0.0]
        lm[4] = [0.40, 0.50, 0.0]  # Thumb close
        lm[8] = [0.41, 0.50, 0.0]  # Index close
        return lm

    def test_no_pinch_when_far(self):
        """No pinch when fingers are far apart."""
        from engine.gestures.recognizer import PinchDetector
        det = PinchDetector()
        lm = self._make_landmarks_far()
        for _ in range(10):
            det.update(lm, time.monotonic())
        assert not det.is_pinched

    def test_pinch_when_close_sustained(self):
        """Pinch confirmed after sustained close proximity."""
        from engine.gestures.recognizer import PinchDetector
        det = PinchDetector()
        lm = self._make_landmarks_close()
        t = time.monotonic()
        for _ in range(10):  # More than CONFIRM_FRAMES
            det.update(lm, t)
            t += 1/30.0
        assert det.is_pinched, f"Expected pinch after sustained close. Distance: {det.pinch_distance:.3f}"


# =============================================================================
# Cursor Engine Tests
# =============================================================================

class TestCursorEngine:
    def test_maps_center_to_screen_center(self):
        """Center of interaction region should map to center of screen."""
        from input.mouse.cursor import CursorEngine, CursorConfig
        config = CursorConfig(screen_width=1920, screen_height=1080)
        engine = CursorEngine(config)
        engine.config.screen_width = 1920
        engine.config.screen_height = 1080

        # Center of interaction region
        center_x = (config.region_left + config.region_right) / 2
        center_y = (config.region_top + config.region_bottom) / 2
        
        # Warm up filter with many frames at center position
        # (dead zone is relative to last position, so after warmup it won't block)
        ts = 0.0
        for _ in range(40):
            sx, sy = engine.update(center_x, center_y, ts)
            ts += 1/30.0
        
        # After warmup, the filter converges to center
        # Center of [0.10, 0.90] mapped to screen = 0.5 * 1920 = 960
        assert abs(sx - 960) < 150, f"Expected ~960, got {sx}"
        assert abs(sy - 540) < 150, f"Expected ~540, got {sy}"

    def test_clamps_to_screen_bounds(self):
        """Extreme positions should be clamped to screen bounds."""
        from input.mouse.cursor import CursorEngine, CursorConfig
        engine = CursorEngine(CursorConfig(screen_width=1920, screen_height=1080))
        engine.config.screen_width = 1920
        engine.config.screen_height = 1080
        engine._filter.reset()

        # Far outside region (0.0, 0.0 = top-left before normalization)
        for _ in range(5):
            sx, sy = engine.update(0.0, 0.0)
        assert sx >= 0 and sy >= 0

        for _ in range(5):
            sx, sy = engine.update(1.0, 1.0)
        assert sx <= 1919 and sy <= 1079


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
