"""
AirOS Engine — Main Orchestrator
Wires the entire real-time pipeline together.

Pipeline (per frame):
  1. Get latest frame from CameraCapture
  2. Submit frame to HandTracker (async, non-blocking)
  3. Get latest tracking result
  4. Process landmarks (geometry)
  5. Update motion estimator
  6. Detect gestures
  7. Run state machine
  8. Execute actions via WindowsInputAdapter
  9. Update telemetry (non-blocking, separate thread)

The dashboard is NOT in this loop. Telemetry is pushed separately.
"""

import time
import logging
import threading
import asyncio
from typing import Optional
from dataclasses import dataclass, field

from engine.camera.capture import CameraCapture, CameraConfig
from engine.tracking.hand_tracker import HandTracker, TrackerConfig
from engine.landmarks.geometry import (
    landmarks_to_array, is_index_only, index_tip_position,
    wrist_position, is_open_palm, normalized_pinch_distance,
)
from engine.motion.estimator import MotionEstimator
from engine.filtering.one_euro import OneEuroFilter2D
from engine.gestures.recognizer import (
    PinchDetector, ScrollDetector, SwipeDetector,
    OpenPalmDetector, TwoHandDetector, GestureEvent,
)
from engine.state.machine import StateMachine
from engine.state.states import InteractionState, GestureType
from engine.calibration.calibrator import CalibrationManager, CalibrationProfile
from input.mouse.cursor import CursorEngine, CursorConfig
from input.windows.send_input import WindowsInputAdapter, VK
from keyboard.air_tap.tap_detector import VirtualKeyboard
from gestures.recognition.studio import GestureStudio
from gestures.registry.manager import GestureRegistry
from gestures.profiles.profile_manager import ProfileManager
from input.windows.foreground import ForegroundAppDetector
from input.action_registry import ActionRegistry

logger = logging.getLogger(__name__)


@dataclass
class Telemetry:
    """Snapshot of engine performance metrics."""
    timestamp: float = 0.0
    state: str = "IDLE"
    gesture: str = "NONE"
    confidence: float = 0.0
    num_hands: int = 0
    fps_current: float = 0.0
    fps_avg: float = 0.0
    fps_min: float = 0.0
    dropped_frames: int = 0
    capture_ms: float = 0.0
    inference_ms: float = 0.0
    gesture_ms: float = 0.0
    total_ms: float = 0.0
    cpu_percent: float = 0.0
    ram_mb: float = 0.0
    enabled: bool = True
    calibration: dict = field(default_factory=dict)
    profile: str = "default"
    foreground_app: str = ""

    def to_dict(self) -> dict:
        return {
            "type": "telemetry",
            "timestamp": self.timestamp,
            "state": self.state,
            "gesture": self.gesture,
            "confidence": round(self.confidence, 3),
            "hands": self.num_hands,
            "fps": {
                "current": round(self.fps_current, 1),
                "avg": round(self.fps_avg, 1),
                "min": round(self.fps_min, 1),
                "dropped": self.dropped_frames,
            },
            "latency": {
                "capture_ms": round(self.capture_ms, 2),
                "inference_ms": round(self.inference_ms, 2),
                "gesture_ms": round(self.gesture_ms, 2),
                "total_ms": round(self.total_ms, 2),
            },
            "system": {
                "cpu_percent": round(self.cpu_percent, 1),
                "ram_mb": round(self.ram_mb, 1),
            },
            "enabled": self.enabled,
            "calibration": self.calibration,
            "profile": self.profile,
            "foreground_app": self.foreground_app,
        }


class AirOSEngine:
    """
    Main AirOS real-time engine.
    
    Usage:
        engine = AirOSEngine()
        engine.start()
        # ... runs until stop() is called
        engine.stop()
    """

    TARGET_LOOP_FPS = 30
    TARGET_LOOP_INTERVAL = 1.0 / TARGET_LOOP_FPS

    def __init__(self, telemetry_callback=None):
        """
        Args:
            telemetry_callback: Optional callable(Telemetry) — called every 100ms
                                 from a separate thread. Non-blocking for main loop.
        """
        self._telemetry_callback = telemetry_callback
        self._running = False
        self._enabled = True  # False = PAUSED or OFF

        # Pipeline components
        self._camera = CameraCapture(CameraConfig(
            camera_index=0,
            width=640,
            height=480,
            fps=30,
            use_dshow=True,
            flip_horizontal=True,
        ))
        self._tracker = HandTracker(TrackerConfig(
            model_path="assets/models/hand_landmarker.task",
            num_hands=2,
        ))
        self._motion = MotionEstimator(history_size=90)
        self._cursor = CursorEngine(CursorConfig())
        self._input = WindowsInputAdapter()

        # Gesture detectors
        self._pinch = PinchDetector()
        self._scroll = ScrollDetector()
        self._swipe = SwipeDetector()
        self._palm = OpenPalmDetector()
        self._two_hand = TwoHandDetector()

        # State machine
        self._state_machine = StateMachine()

        # Calibration
        self._calibration = CalibrationManager()
        self._calibration.load()  # Load saved profile if present
        self._apply_calibration_profile()
        self._calibration_active = False

        # Virtual keyboard
        self._keyboard = VirtualKeyboard()

        # Gesture Studio (custom gestures)
        self._studio = GestureStudio()
        self._studio_actions = ActionRegistry(self._input)

        # Gesture registry + app profiles
        self._registry = GestureRegistry()
        self._registry.load()
        self._profile_manager = ProfileManager(
            registry=self._registry,
            foreground_detector=ForegroundAppDetector(),
        )
        self._profile_manager.on_profile_changed(self._on_profile_changed)
        self._apply_gesture_thresholds()

        # Telemetry state
        self._telemetry = Telemetry()
        self._telemetry_lock = threading.Lock()
        self._last_telemetry_time = 0.0

        # Performance tracking
        self._frame_count = 0
        self._last_frame_ts = 0.0
        self._current_gesture = GestureType.NONE
        self._current_confidence = 0.0

        # Safety: track last gesture event for telemetry
        self._last_gesture_event: Optional[GestureEvent] = None

        # Timestamp counter for MediaPipe (must be monotonically increasing)
        self._mp_timestamp_ms = 0

        # psutil for system metrics
        self._process = None
        try:
            import psutil
            import os
            self._process = psutil.Process(os.getpid())
        except ImportError:
            pass

    def start(self) -> bool:
        """Initialize and start the engine. Returns True on success."""
        logger.info("=== AirOS Engine Starting ===")

        # Initialize cursor engine (detects screen size)
        self._cursor.initialize()

        # Initialize tracker
        if not self._tracker.initialize():
            logger.error("HandTracker initialization failed")
            return False

        # Start camera
        if not self._camera.start():
            logger.error("Camera start failed")
            return False

        camera_info = self._camera.get_camera_info()
        logger.info(f"Camera: {camera_info}")

        self._running = True
        self._main_loop()
        return True

    def _main_loop(self):
        """
        Main real-time processing loop.
        Runs on the calling thread. Must not be blocked.
        """
        logger.info("Real-time pipeline started")
        last_result_timestamp = -1.0

        while self._running:
            loop_start = time.monotonic()
            if getattr(self, "_max_frames", None) is not None and self._frame_count >= self._max_frames:
                logger.info(f"Max frames reached ({self._max_frames}) — stopping")
                self.stop()
                break

            # ── 1. Get latest frame ──────────────────────────────────
            frame, frame_ts = self._camera.get_frame()
            if frame is None:
                time.sleep(0.001)
                continue
            self._frame_count += 1

            # ── 2. Submit to MediaPipe (non-blocking async) ──────────
            self._mp_timestamp_ms += 1  # Must increase monotonically
            self._tracker.process_frame(frame, self._mp_timestamp_ms)

            # ── 3. Get latest tracking result ────────────────────────
            t_gesture_start = time.monotonic()
            result = self._tracker.get_latest_result()

            if result is None or result.num_hands == 0:
                # No hands — reset detectors and motion
                self._handle_no_hands()
                self._current_gesture = GestureType.NONE
                self._current_confidence = 0.0
                self._update_telemetry(result, 0.0, frame_ts)
                self._sleep_to_target(loop_start)
                continue

            # ── 4. Process landmarks ─────────────────────────────────
            landmarks = result.landmarks[0]  # Primary hand

            # ── 4b. Calibration workflow ─────────────────────────────
            if self._calibration_active:
                wrist = wrist_position(landmarks)
                pdist = normalized_pinch_distance(landmarks)
                complete = self._calibration.update(
                    landmarks,
                    num_hands=result.num_hands,
                    wrist_pos=wrist,
                    pinch_dist=pdist,
                )
                if complete:
                    self.stop_calibration(apply=True)
                self._update_telemetry(result, 0.0, frame_ts)
                self._sleep_to_target(loop_start)
                continue

            # ── 5. Update motion estimator ───────────────────────────
            wrist_pos = wrist_position(landmarks)
            motion = self._motion.update(wrist_pos[0], wrist_pos[1], time.monotonic())

            # ── 4c. App profile auto-switch (rate-limited ~1 Hz) ─────
            self._profile_manager.update(time.monotonic())

            # ── 6. Detect gestures ───────────────────────────────────
            ts = time.monotonic()
            
            # Index pointer
            has_index_ptr = is_index_only(landmarks)
            
            # Pinch
            pinch_state_change = self._pinch.update(landmarks, ts)
            is_pinched = self._pinch.is_pinched
            is_approaching = self._pinch.is_approaching

            # If pinched, don't detect scroll or swipe
            gesture_event: Optional[GestureEvent] = None

            if not is_pinched and self._state_machine.state != InteractionState.DRAG:
                # Scroll
                scroll_event = self._scroll.update(motion.velocity[1], ts)
                if scroll_event:
                    gesture_event = scroll_event

                # Swipe (only if not scrolling)
                if gesture_event is None:
                    swipe_event = self._swipe.update(
                        motion.displacement_medium[0],
                        motion.displacement_medium[1],
                        motion.velocity[0],
                        ts,
                    )
                    if swipe_event:
                        gesture_event = swipe_event

            # Open palm (PAUSE) — always check
            palm_event = self._palm.update(landmarks, motion.speed, ts)
            if palm_event:
                gesture_event = palm_event

            # Two hands
            two_hand_event = self._two_hand.update(result.num_hands, ts)
            if two_hand_event:
                gesture_event = two_hand_event

            # ── 6b. Custom gestures (Gesture Studio) ─────────────────
            custom_id = None
            if self._enabled and not is_pinched:
                custom_id = self._studio.match(landmarks, ts)
                if custom_id:
                    self._execute_custom_gesture(custom_id)

            # Determine current gesture type for state machine
            if gesture_event:
                current_gesture = gesture_event.gesture
                self._current_confidence = gesture_event.confidence
            elif is_pinched:
                current_gesture = GestureType.PINCH
                self._current_confidence = self._pinch.get_confidence()
            elif has_index_ptr:
                current_gesture = GestureType.INDEX_POINTER
                self._current_confidence = 0.85
            else:
                current_gesture = GestureType.NONE
                self._current_confidence = 0.0

            self._current_gesture = current_gesture

            gesture_ms = (time.monotonic() - t_gesture_start) * 1000

            # ── 7. Run state machine ─────────────────────────────────
            if self._enabled:
                actions = self._state_machine.process(
                    gesture=current_gesture,
                    is_pinched=is_pinched,
                    is_pinch_approaching=is_approaching,
                    num_hands=result.num_hands,
                    has_index_pointer=has_index_ptr,
                    speed=motion.speed,
                    gesture_event=gesture_event,
                )

                # ── 8. Execute actions ───────────────────────────────
                if actions:
                    self._execute_actions(actions, landmarks, gesture_event)

            # ── 8b. Virtual keyboard mode ────────────────────────────
            if self._state_machine.state == InteractionState.KEYBOARD:
                self._run_keyboard(landmarks, ts)

            # ── 9. Telemetry snapshot ────────────────────────────────
            total_ms = (time.monotonic() - loop_start) * 1000
            self._update_telemetry(result, gesture_ms, frame_ts, total_ms)

            # ── Sleep to maintain target FPS ─────────────────────────
            self._sleep_to_target(loop_start)

        logger.info("Real-time pipeline stopped")

    def _execute_actions(self, actions: list[str], landmarks, gesture_event: Optional[GestureEvent]):
        """Map action strings to actual SendInput calls."""
        for action in actions:
            try:
                if action == "cursor_move":
                    index_pos = index_tip_position(landmarks)
                    sx, sy = self._cursor.update(index_pos[0], index_pos[1])
                    self._input.move_cursor(sx, sy)

                elif action == "left_click":
                    self._input.left_click()

                elif action == "mouse_down":
                    self._input.mouse_down("left")

                elif action == "mouse_up":
                    self._input.mouse_up("left")

                elif action in ("scroll_up", "gesture_type.scroll_up"):
                    intensity = gesture_event.extra.get("intensity", 0.5) if gesture_event else 0.5
                    lines = max(1, min(5, int(intensity * 5)))
                    self._input.scroll_up(lines)

                elif action in ("scroll_down", "gesture_type.scroll_down"):
                    intensity = gesture_event.extra.get("intensity", 0.5) if gesture_event else 0.5
                    lines = max(1, min(5, int(intensity * 5)))
                    self._input.scroll_down(lines)

                elif action == "navigate_back":
                    self._input.key_press(VK.BROWSER_BACK)

                elif action == "navigate_forward":
                    self._input.key_press(VK.BROWSER_FORWARD)

                elif action == "pause":
                    self._input.disable()
                    self._enabled = False
                    logger.info("AirOS PAUSED")

                elif action == "resume":
                    self._input.enable()
                    self._enabled = True
                    logger.info("AirOS RESUMED")

                elif action == "enter_keyboard":
                    self._keyboard.activate()
                    logger.info("Virtual keyboard activated")

                elif action == "exit_keyboard":
                    self._keyboard.deactivate()
                    logger.info("Virtual keyboard deactivated")

            except Exception as e:
                logger.error(f"Action '{action}' failed: {e}")

    def _execute_custom_gesture(self, template_id: str):
        """Execute the safe action bound to a matched custom gesture template."""
        try:
            template = self._studio.get_template(template_id)
            if template is None:
                logger.warning(f"Custom gesture template not found: {template_id}")
                return
            action = template.action
            if not self._studio_actions.is_valid_action(action):
                logger.warning(
                    f"Custom gesture '{template.name}' has invalid action '{action}' — ignored"
                )
                return
            ok = self._studio_actions.execute(action)
            if ok:
                logger.info(f"Custom gesture fired: {template.name} -> {action}")
        except Exception as e:
            logger.error(f"Custom gesture execution error: {e}")

    def _run_keyboard(self, landmarks, timestamp: float):
        """
        Virtual keyboard interaction: maps the index fingertip to a key and
        executes air-tap key presses. Runs only while in KEYBOARD state.
        """
        try:
            index_pos = index_tip_position(landmarks)
            key_action = self._keyboard.update(index_pos[0], index_pos[1], timestamp)
            if key_action is None:
                return

            if key_action == "space":
                self._input.key_press(VK.SPACE)
            elif key_action == "backspace":
                self._input.key_press(VK.BACK)
            elif key_action == "enter":
                self._input.key_press(VK.RETURN)
            elif key_action == "shift":
                self._input.key_press(VK.SHIFT)
            elif len(key_action) == 1:
                self._input.type_unicode(key_action)
            else:
                logger.warning(f"Unknown keyboard action: {key_action}")
        except Exception as e:
            logger.error(f"Virtual keyboard error: {e}")

    def _handle_no_hands(self):
        """Clean up when tracking is lost."""
        if self._state_machine.state == InteractionState.DRAG:
            try:
                self._input.mouse_up("left")
            except Exception:
                pass
        was_keyboard = self._state_machine.state == InteractionState.KEYBOARD
        self._pinch.reset()
        self._motion.reset()
        self._cursor.reset_filter()
        actions = self._state_machine.process(
            gesture=GestureType.NONE,
            is_pinched=False,
            is_pinch_approaching=False,
            num_hands=0,
            has_index_pointer=False,
            speed=0.0,
        )
        # Execute cleanup actions (e.g. exit_keyboard when a hand is lost)
        if actions and was_keyboard:
            for action in actions:
                if action == "exit_keyboard":
                    self._keyboard.deactivate()
                elif action == "mouse_up":
                    try:
                        self._input.mouse_up("left")
                    except Exception:
                        pass

    def _update_telemetry(self, result, gesture_ms: float, frame_ts: float, total_ms: float = 0.0):
        """Update telemetry snapshot. Rate-limited to 10 Hz."""
        now = time.monotonic()
        if now - self._last_telemetry_time < 0.1:  # 10 Hz
            return
        self._last_telemetry_time = now

        cam_metrics = self._camera.metrics
        tracking_result = result

        cpu = 0.0
        ram = 0.0
        if self._process:
            try:
                cpu = self._process.cpu_percent(interval=None)
                ram = self._process.memory_info().rss / (1024 * 1024)
            except Exception:
                pass

        with self._telemetry_lock:
            self._telemetry = Telemetry(
                timestamp=now,
                state=self._state_machine.state.name,
                gesture=self._current_gesture.name if self._current_gesture else "NONE",
                confidence=self._current_confidence,
                num_hands=tracking_result.num_hands if tracking_result else 0,
                fps_current=cam_metrics.actual_fps,
                fps_avg=cam_metrics.avg_fps,
                fps_min=cam_metrics.min_fps,
                dropped_frames=cam_metrics.dropped_frames,
                capture_ms=cam_metrics.capture_time_ms,
                inference_ms=tracking_result.inference_time_ms if tracking_result else 0.0,
                gesture_ms=gesture_ms,
                total_ms=total_ms,
                cpu_percent=cpu,
                ram_mb=ram,
                enabled=self._enabled,
                calibration=self.get_calibration_status(),
                profile=self._profile_manager.active_profile_id,
                foreground_app=self._profile_manager.last_app,
            )

        if self._telemetry_callback:
            try:
                self._telemetry_callback(self._telemetry)
            except Exception as e:
                logger.error(f"Telemetry callback error: {e}")

    def get_telemetry(self) -> Telemetry:
        """Thread-safe telemetry snapshot."""
        with self._telemetry_lock:
            return self._telemetry

    def _sleep_to_target(self, loop_start: float):
        """Sleep for the remaining time in the target loop interval."""
        elapsed = time.monotonic() - loop_start
        sleep_time = self.TARGET_LOOP_INTERVAL - elapsed
        if sleep_time > 0.001:
            time.sleep(sleep_time)

    def pause(self):
        """Pause gesture input (camera continues)."""
        self._enabled = False
        self._input.disable()
        self._state_machine.force_state(InteractionState.PAUSED)
        logger.info("Engine PAUSED")

    def resume(self):
        """Resume gesture input."""
        self._enabled = True
        self._input.enable()
        self._state_machine.force_state(InteractionState.POINTER)
        logger.info("Engine RESUMED")

    def start_calibration(self):
        """Start the guided calibration workflow."""
        self._calibration_active = True
        self._enabled = False  # Disable gesture input during calibration
        self._input.disable()
        self._calibration.start()
        self._state_machine.force_state(InteractionState.CALIBRATION)
        logger.info("Calibration started")

    def stop_calibration(self, apply: bool = True):
        """Stop calibration. If apply=True, saves the resulting profile."""
        self._calibration_active = False
        if apply:
            self._calibration.save()
            self._apply_calibration_profile()
        self._state_machine.force_state(InteractionState.IDLE)
        logger.info("Calibration stopped")

    @property
    def is_calibrating(self) -> bool:
        return self._calibration_active

    def get_calibration_status(self) -> dict:
        return self._calibration.get_status()

    def _apply_calibration_profile(self):
        """Apply the calibration profile to cursor and gesture detectors."""
        p = self._calibration.profile
        if not isinstance(p, CalibrationProfile):
            return
        self._cursor.update_config(
            region_left=p.region_left,
            region_right=p.region_right,
            region_top=p.region_top,
            region_bottom=p.region_bottom,
            sensitivity=p.sensitivity,
            one_euro_min_cutoff=p.smoothing_min_cutoff,
            one_euro_beta=p.smoothing_beta,
        )
        self._pinch.PINCH_THRESHOLD = p.pinch_threshold
        self._pinch.RELEASE_THRESHOLD = p.release_threshold
        self._scroll.SCROLL_VELOCITY_THRESHOLD = p.scroll_velocity_threshold
        self._swipe.MIN_DISPLACEMENT = p.swipe_displacement_threshold
        self._swipe.MIN_VELOCITY = p.swipe_velocity_threshold
        logger.info(
            f"Calibration profile applied: "
            f"pinch={p.pinch_threshold:.2f} region=({p.region_left:.2f},{p.region_top:.2f})"
            f"-({p.region_right:.2f},{p.region_bottom:.2f}) sensitivity={p.sensitivity:.2f}"
        )

    def _on_profile_changed(self, profile_id: str):
        """Re-apply gesture thresholds when the active app profile changes."""
        self._apply_gesture_thresholds()
        logger.info(f"App profile changed -> {profile_id}: thresholds reapplied")

    def _apply_gesture_thresholds(self):
        """Apply gesture thresholds (with active profile overrides) from the
        registry to the detector classes."""
        try:
            pinch = self._registry.get_by_id("pinch_click")
            if pinch and pinch.thresholds.get("distance"):
                self._pinch.PINCH_THRESHOLD = float(pinch.thresholds["distance"])

            scroll = self._registry.get_by_id("scroll_down")
            if scroll and scroll.thresholds.get("velocity"):
                self._scroll.SCROLL_VELOCITY_THRESHOLD = float(scroll.thresholds["velocity"])

            swipe = self._registry.get_by_id("swipe_left")
            if swipe:
                if swipe.thresholds.get("displacement"):
                    self._swipe.MIN_DISPLACEMENT = float(swipe.thresholds["displacement"])
                if swipe.thresholds.get("velocity"):
                    self._swipe.MIN_VELOCITY = float(swipe.thresholds["velocity"])

            palm = self._registry.get_by_id("open_palm")
            if palm:
                if palm.thresholds.get("hold_duration"):
                    self._palm.HOLD_DURATION = float(palm.thresholds["hold_duration"])

            two_hand = self._registry.get_by_id("two_hands")
            if two_hand:
                if two_hand.thresholds.get("hold_duration"):
                    self._two_hand.HOLD_DURATION = float(two_hand.thresholds["hold_duration"])
        except Exception as e:
            logger.error(f"Failed to apply gesture thresholds: {e}")

    def studio_start_recording(self):
        """Start recording a custom gesture."""
        self._studio.start_recording()
        logger.info("Gesture recording started")

    def studio_finish_recording(self, name: str = "Custom Gesture"):
        """Finish recording and save the custom gesture template."""
        template = self._studio.finish_recording(name)
        if template is None:
            logger.warning("Gesture recording failed (too few frames?)")
            return None
        logger.info(f"Gesture recorded: {template.name} ({template.id})")
        return template.to_dict()

    def studio_cancel_recording(self):
        self._studio.cancel_recording()
        logger.info("Gesture recording cancelled")

    def studio_list(self) -> list:
        return self._studio.list_templates()

    def studio_delete(self, template_id: str) -> bool:
        return self._studio.delete_template(template_id)

    def studio_rename(self, template_id: str, new_name: str) -> bool:
        return self._studio.rename_template(template_id, new_name)

    def studio_set_action(self, template_id: str, action: str) -> bool:
        if not self._studio_actions.is_valid_action(action):
            logger.warning(f"Invalid action for custom gesture: {action}")
            return False
        return self._studio.set_template_action(template_id, action)

    # ── App profiles ──────────────────────────────────────────────────
    def profile_set(self, profile_id: str) -> bool:
        return self._profile_manager.set_profile(profile_id)

    def profile_list(self) -> list:
        return [p.to_dict() for p in self._registry.get_profiles()]

    def profile_current(self) -> dict:
        p = self._registry.active_profile
        return p.to_dict() if p else {"id": "default", "name": "Default"}

    def profile_get_overrides(self, profile_id: str) -> dict:
        p = self._registry.get_profile(profile_id)
        return p.gesture_overrides if p else {}

    def profile_set_override(self, profile_id: str, gesture_id: str,
                             override: dict) -> bool:
        p = self._registry.get_profile(profile_id)
        if p is None:
            return False
        p.gesture_overrides[gesture_id] = override
        return self._registry.update_profile(p)

    def stop(self):
        """Stop the engine gracefully."""
        logger.info("Stopping AirOS engine...")
        self._running = False
        self._input.disable()
        self._camera.stop()
        self._tracker.close()
        logger.info("AirOS engine stopped")
