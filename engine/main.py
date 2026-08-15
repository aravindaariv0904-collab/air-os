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
  7. Run state machine & arbitration
  8. Execute actions via WindowsInputAdapter & InputSafetyManager
  9. Update telemetry (non-blocking, separate thread)
"""

import time
import logging
import threading
import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

from config.config_manager import get_config_manager, AppConfigModel
from input.safety_manager import get_safety_manager, InputSafetyManager
from engine.lifecycle import get_lifecycle_manager, EngineLifecycleManager, EngineState

from engine.camera.capture import CameraCapture, CameraConfig
from engine.tracking.hand_tracker import HandTracker, TrackerConfig
from engine.landmarks.geometry import (
    landmarks_to_array, is_index_only, index_tip_position,
    wrist_position, is_open_palm, normalized_pinch_distance,
)
from engine.motion.estimator import MotionEstimator
from engine.filtering.one_euro import OneEuroFilter2D
from engine.gestures.recognizer import (
    PinchDetector, PinchState, ScrollDetector, SwipeDetector,
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
from gestures.arbitration.arbitrator import GestureArbitrator
from input.windows.foreground import ForegroundAppDetector
from input.action_registry import ActionRegistry

from engine.telemetry.latency import LatencyTracker, StageTimestamps, LatencyBreakdown

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
    latency_breakdown: LatencyBreakdown = field(default_factory=LatencyBreakdown)

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
                "p50_ms": round(self.latency_breakdown.p50_ms, 2),
                "p95_ms": round(self.latency_breakdown.p95_ms, 2),
                "p99_ms": round(self.latency_breakdown.p99_ms, 2),
                "detail": self.latency_breakdown.to_dict(),
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
    """

    def __init__(self, telemetry_callback=None):
        self._telemetry_callback = telemetry_callback
        self._running = False
        self._enabled = True  # False = PAUSED or OFF

        # Service singletons
        self._config_mgr = get_config_manager()
        self._lifecycle_mgr = get_lifecycle_manager()
        self._input = WindowsInputAdapter()
        self._safety_mgr = get_safety_manager(self._input)

        # Apply target loop interval from config
        sys_cfg = self._config_mgr.config.system
        self._target_loop_fps = sys_cfg.target_loop_fps
        self._target_loop_interval = 1.0 / self._target_loop_fps

        # Pipeline components
        self._camera = CameraCapture(CameraConfig(
            camera_index=sys_cfg.camera_index,
            width=sys_cfg.camera_width,
            height=sys_cfg.camera_height,
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
        self._apply_cursor_config()

        # Gesture detectors
        self._pinch = PinchDetector()
        self._scroll = ScrollDetector()
        self._swipe = SwipeDetector()
        self._palm = OpenPalmDetector()
        self._two_hand = TwoHandDetector()

        # State machine & Arbitrator
        self._state_machine = StateMachine()
        self._arbitrator = GestureArbitrator()

        # Calibration
        self._calibration = CalibrationManager()
        self._calibration.load()
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

        # Telemetry & Latency state
        self._telemetry = Telemetry()
        self._telemetry_lock = threading.Lock()
        self._last_telemetry_time = 0.0
        self._latency_tracker = LatencyTracker()

        # Performance tracking
        self._frame_count = 0
        self._last_frame_ts = 0.0
        self._current_gesture = GestureType.NONE
        self._current_confidence = 0.0

        # Safety: track last gesture event for telemetry
        self._last_gesture_event: Optional[GestureEvent] = None

        # Timestamp counter for MediaPipe
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
        self._lifecycle_mgr.transition_to(EngineState.STARTING)

        # Initialize cursor engine (detects screen size)
        self._cursor.initialize()

        # Initialize tracker
        if not self._tracker.initialize():
            logger.error("HandTracker initialization failed")
            self._lifecycle_mgr.transition_to(EngineState.ERROR, "HandTracker initialization failed")
            return False

        # Start camera
        if not self._camera.start():
            logger.error("Camera start failed")
            self._lifecycle_mgr.transition_to(EngineState.ERROR, "Camera start failed")
            return False

        camera_info = self._camera.get_camera_info()
        logger.info(f"Camera: {camera_info}")

        self._running = True
        self._lifecycle_mgr.transition_to(EngineState.READY)
        self._lifecycle_mgr.transition_to(EngineState.RUNNING)
        self._main_loop()
        return True

    def _main_loop(self):
        """
        Main real-time processing loop.
        Runs on the calling thread. Must not be blocked.
        """
        logger.info("Real-time pipeline started")
        last_result_timestamp = -1.0
        last_frame_id = -1

        while self._running:
            loop_start = time.monotonic()
            if getattr(self, "_max_frames", None) is not None and self._frame_count >= self._max_frames:
                logger.info(f"Max frames reached ({self._max_frames}) — stopping")
                self.stop()
                break

            # 1. Get latest frame
            frame, frame_ts, frame_id = self._camera.get_frame()
            if frame is None:
                time.sleep(0.001)
                continue
            self._frame_count += 1

            ts_stage = StageTimestamps(frame_id=frame_id, capture_ts=frame_ts)

            # 2. Submit to MediaPipe (non-blocking async)
            self._mp_timestamp_ms += 1
            ts_stage.submit_ts = time.monotonic()
            self._tracker.process_frame(
                frame,
                self._mp_timestamp_ms,
                frame_id=frame_id,
                capture_timestamp=frame_ts,
            )

            # 3. Get latest tracking result
            t_gesture_start = time.monotonic()
            result = self._tracker.get_latest_result()

            if result is None:
                self._handle_no_hands()
                self._current_gesture = GestureType.NONE
                self._current_confidence = 0.0
                self._update_telemetry(result, 0.0, frame_ts)
                self._sleep_to_target(loop_start)
                continue

            # Check if this result has already been processed
            if result.result_timestamp <= last_result_timestamp or (result.frame_id > 0 and result.frame_id == last_frame_id):
                self._sleep_to_target(loop_start)
                continue

            last_result_timestamp = result.result_timestamp
            last_frame_id = result.frame_id
            ts_stage.tracking_result_ts = result.result_timestamp

            if result.num_hands == 0:
                self._handle_no_hands()
                self._current_gesture = GestureType.NONE
                self._current_confidence = 0.0
                self._update_telemetry(result, 0.0, frame_ts)
                self._sleep_to_target(loop_start)
                continue

            # 4. Process landmarks
            landmarks = result.landmarks[0]

            # 4b. Calibration workflow
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

            # 4c. Custom gesture studio recording
            if self._studio.is_recording:
                self._studio.add_frame(landmarks)

            ts_stage.landmark_ts = time.monotonic()

            # 5. Motion estimation
            wrist = wrist_position(landmarks)
            motion = self._motion.update(wrist[0], wrist[1], result.result_timestamp)

            # 6. Gesture detection
            pinch_state = self._pinch.update(landmarks, result.result_timestamp)
            pinch_event = (
                GestureEvent(gesture=GestureType.PINCH, confidence=self._pinch.get_confidence(), timestamp=result.result_timestamp)
                if pinch_state == PinchState.PINCHED else None
            )
            scroll_event = self._scroll.update(motion.velocity[1], result.result_timestamp)
            swipe_event = self._swipe.update(
                motion.displacement_short[0],
                motion.displacement_short[1],
                motion.velocity[0],
                result.result_timestamp
            )
            palm_event = self._palm.update(landmarks, motion.speed, result.result_timestamp)
            two_hand_event = self._two_hand.update(result.num_hands, result.result_timestamp)

            # Evaluate system gesture candidate
            system_gesture_event: Optional[GestureEvent] = (
                palm_event or two_hand_event or pinch_event or scroll_event or swipe_event
            )

            # Evaluate custom gesture candidate
            custom_gesture_id: Optional[str] = None
            if system_gesture_event is None and not self._pinch.is_pinched:
                custom_gesture_id = self._studio.match(landmarks, result.result_timestamp)

            # Arbitrate
            has_index_ptr = is_index_only(landmarks)
            is_pinched = self._pinch.is_pinched
            is_approaching = self._pinch.is_approaching

            gesture_event, matched_custom_id = self._arbitrator.arbitrate(
                system_event=system_gesture_event,
                custom_gesture_id=custom_gesture_id,
                is_pinched=is_pinched,
                is_paused=not self._enabled,
                is_calibrating=self._calibration_active,
                is_keyboard=self._state_machine.state == InteractionState.KEYBOARD,
            )

            if matched_custom_id:
                self._execute_custom_gesture(matched_custom_id)

            current_gesture = GestureType.NONE
            if gesture_event:
                current_gesture = gesture_event.gesture
                self._current_confidence = gesture_event.confidence
            elif is_pinched:
                current_gesture = GestureType.PINCH
                self._current_confidence = 0.95
            elif has_index_ptr:
                current_gesture = GestureType.INDEX_POINTER
                self._current_confidence = 0.85
            else:
                current_gesture = GestureType.NONE
                self._current_confidence = 0.0

            self._current_gesture = current_gesture
            ts_stage.gesture_ts = time.monotonic()
            gesture_ms = (ts_stage.gesture_ts - t_gesture_start) * 1000

            # 7. Run state machine
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
                ts_stage.state_ts = time.monotonic()

                # 8. Execute actions
                if actions:
                    self._execute_actions(actions, landmarks, gesture_event)
                ts_stage.input_ts = time.monotonic()
            else:
                ts_stage.state_ts = time.monotonic()
                ts_stage.input_ts = ts_stage.state_ts

            # 8b. Virtual keyboard mode
            if self._state_machine.state == InteractionState.KEYBOARD:
                self._run_keyboard(landmarks, result.result_timestamp)

            # Record full stage breakdown
            latency_breakdown = self._latency_tracker.record_frame(ts_stage)

            # 9. Telemetry snapshot
            total_ms = (time.monotonic() - loop_start) * 1000
            self._update_telemetry(result, gesture_ms, frame_ts, total_ms, latency_breakdown)

            # Sleep to maintain target FPS
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
                    self._safety_mgr.record_mouse_down("left")

                elif action == "mouse_up":
                    self._input.mouse_up("left")
                    self._safety_mgr.record_mouse_up("left")

                elif action in ("scroll_up", "gesture_type.scroll_up"):
                    intensity = gesture_event.extra.get("intensity", 0.5) if gesture_event else 0.5
                    lines = max(1, min(10, int(intensity * self._config_mgr.config.gestures.scroll_speed * 2)))
                    self._input.scroll_up(lines)

                elif action in ("scroll_down", "gesture_type.scroll_down"):
                    intensity = gesture_event.extra.get("intensity", 0.5) if gesture_event else 0.5
                    lines = max(1, min(10, int(intensity * self._config_mgr.config.gestures.scroll_speed * 2)))
                    self._input.scroll_down(lines)

                elif action == "navigate_back":
                    self._input.key_press(VK.BROWSER_BACK)

                elif action == "navigate_forward":
                    self._input.key_press(VK.BROWSER_FORWARD)

                elif action == "pause":
                    self.pause()

                elif action == "resume":
                    self.resume()

                elif action == "enter_keyboard":
                    self._keyboard.activate()
                    self._safety_mgr.set_keyboard_mode(True)
                    logger.info("Virtual keyboard activated")

                elif action == "exit_keyboard":
                    self._keyboard.deactivate()
                    self._safety_mgr.set_keyboard_mode(False)
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
        """Virtual keyboard interaction."""
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
        self._safety_mgr.release_all_held_input(reason="tracking_loss")
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
        if actions and was_keyboard:
            for action in actions:
                if action == "exit_keyboard":
                    self._keyboard.deactivate()
                    self._safety_mgr.set_keyboard_mode(False)

    def _update_telemetry(
        self,
        result,
        gesture_ms: float,
        frame_ts: float,
        total_ms: float = 0.0,
        latency_breakdown: Optional[LatencyBreakdown] = None,
    ):
        """Update telemetry snapshot."""
        now = time.monotonic()
        if now - self._last_telemetry_time < 0.1:
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

        if latency_breakdown is None:
            latency_breakdown = self._latency_tracker.current_breakdown

        with self._telemetry_lock:
            self._telemetry = Telemetry(
                timestamp=now,
                state=self._lifecycle_mgr.state.value.upper() if self._enabled else "PAUSED",
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
                latency_breakdown=latency_breakdown,
            )

        if self._telemetry_callback:
            try:
                self._telemetry_callback(self._telemetry)
            except Exception as e:
                logger.error(f"Telemetry callback error: {e}")

    def get_telemetry(self) -> Telemetry:
        with self._telemetry_lock:
            return self._telemetry

    def _sleep_to_target(self, loop_start: float):
        elapsed = time.monotonic() - loop_start
        sleep_time = self._target_loop_interval - elapsed
        if sleep_time > 0.001:
            time.sleep(sleep_time)

    def pause(self):
        """Pause gesture input."""
        self._enabled = False
        self._safety_mgr.release_all_held_input(reason="pause")
        self._input.disable()
        self._state_machine.force_state(InteractionState.PAUSED)
        self._lifecycle_mgr.transition_to(EngineState.PAUSED)
        logger.info("Engine PAUSED")

    def resume(self):
        """Resume gesture input."""
        self._enabled = True
        self._input.enable()
        self._state_machine.force_state(InteractionState.POINTER)
        self._lifecycle_mgr.transition_to(EngineState.RUNNING)
        logger.info("Engine RESUMED")

    def start_calibration(self):
        """Start guided calibration."""
        self._calibration_active = True
        self._enabled = False
        self._safety_mgr.release_all_held_input(reason="calibration_start")
        self._input.disable()
        self._calibration.start()
        self._state_machine.force_state(InteractionState.CALIBRATION)
        logger.info("Calibration started")

    def stop_calibration(self, apply: bool = True):
        """Stop calibration."""
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

    def _apply_cursor_config(self):
        """Apply CursorConfigModel from authoritative ConfigManager."""
        c = self._config_mgr.config.cursor
        self._cursor.update_config(
            region_left=c.region_left,
            region_right=c.region_right,
            region_top=c.region_top,
            region_bottom=c.region_bottom,
            dead_zone=c.dead_zone,
            sensitivity=c.sensitivity,
            one_euro_min_cutoff=c.smoothing_min_cutoff,
            one_euro_beta=c.smoothing_beta,
            one_euro_d_cutoff=c.smoothing_d_cutoff,
        )

    def _apply_calibration_profile(self):
        """Apply calibration profile."""
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

    def settings_update(self, patch: Dict[str, Any]) -> dict:
        """Update authoritative configuration from settings IPC command."""
        updated = self._config_mgr.update_dict(patch)
        self._apply_cursor_config()
        self._apply_gesture_thresholds()
        return updated.to_dict()

    def settings_get(self) -> dict:
        """Get authoritative configuration as dict."""
        return self._config_mgr.config.to_dict()

    def _on_profile_changed(self, profile_id: str):
        self._apply_gesture_thresholds()

    def _apply_gesture_thresholds(self):
        try:
            g_cfg = self._config_mgr.config.gestures
            self._pinch.PINCH_THRESHOLD = g_cfg.pinch_threshold
            self._pinch.RELEASE_THRESHOLD = g_cfg.release_threshold
            self._scroll.SCROLL_VELOCITY_THRESHOLD = g_cfg.scroll_velocity_threshold
            self._swipe.MIN_DISPLACEMENT = g_cfg.swipe_displacement_threshold
            self._swipe.MIN_VELOCITY = g_cfg.swipe_velocity_threshold
            self._palm.HOLD_DURATION = g_cfg.open_palm_hold_sec
            self._two_hand.HOLD_DURATION = g_cfg.two_hand_hold_sec
        except Exception as e:
            logger.error(f"Failed to apply gesture thresholds: {e}")

    def studio_start_recording(self):
        self._studio.start_recording()
        logger.info("Gesture recording started")

    def studio_finish_recording(self, name: str = "Custom Gesture"):
        template = self._studio.finish_recording(name)
        if template is None:
            logger.warning("Gesture recording failed")
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

    def profile_set_override(self, profile_id: str, gesture_id: str, override: dict) -> bool:
        p = self._registry.get_profile(profile_id)
        if p is None:
            return False
        p.gesture_overrides[gesture_id] = override
        return self._registry.update_profile(p)

    def stop(self):
        """Stop the engine gracefully."""
        logger.info("Stopping AirOS engine...")
        self._lifecycle_mgr.transition_to(EngineState.STOPPING)
        self._running = False
        self._safety_mgr.release_all_held_input(reason="stop")
        self._input.disable()
        self._camera.stop()
        self._tracker.close()
        self._lifecycle_mgr.transition_to(EngineState.STOPPED)
        logger.info("AirOS engine stopped")
