"""
AirOS Engine — Camera Capture Module
Handles webcam access using OpenCV with DirectShow backend for low latency.

Strategy:
- Uses CAP_DSHOW backend (Windows) for minimum capture latency.
- Buffer size set to 1 to avoid stale frame buildup.
- latest-frame strategy: grab() + retrieve() pattern to skip buffered frames.
- Measures actual FPS and capture time per frame.
"""

import cv2
import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    """Camera configuration parameters."""
    camera_index: int = 0
    width: int = 640
    height: int = 480
    fps: int = 30
    use_dshow: bool = True       # DirectShow backend (Windows, lower latency)
    buffer_size: int = 1         # Minimize internal buffer
    flip_horizontal: bool = True # Mirror so user sees natural reflection


@dataclass
class CameraMetrics:
    """Real-time camera performance metrics."""
    actual_fps: float = 0.0
    avg_fps: float = 0.0
    min_fps: float = float('inf')
    capture_time_ms: float = 0.0
    dropped_frames: int = 0
    total_frames: int = 0
    _fps_window: list = field(default_factory=list)
    _fps_window_size: int = 30   # Rolling window for FPS calculation

    def update(self, capture_time: float, dropped: bool = False):
        """Update metrics after each frame."""
        self.total_frames += 1
        self.capture_time_ms = capture_time * 1000
        if dropped:
            self.dropped_frames += 1
        
        if capture_time > 0:
            fps = 1.0 / capture_time
            self._fps_window.append(fps)
            if len(self._fps_window) > self._fps_window_size:
                self._fps_window.pop(0)
            self.actual_fps = fps
            self.avg_fps = sum(self._fps_window) / len(self._fps_window)
            self.min_fps = min(self._fps_window)

    def to_dict(self) -> dict:
        return {
            "actual_fps": round(self.actual_fps, 1),
            "avg_fps": round(self.avg_fps, 1),
            "min_fps": round(self.min_fps, 1),
            "capture_ms": round(self.capture_time_ms, 2),
            "dropped": self.dropped_frames,
            "total": self.total_frames,
        }


class CameraCapture:
    """
    Thread-safe camera capture with latest-frame strategy.
    
    The camera runs in its own thread. The processing pipeline
    always gets the NEWEST available frame, never a stale one.
    """

    def __init__(self, config: Optional[CameraConfig] = None):
        self.config = config or CameraConfig()
        self.metrics = CameraMetrics()
        self._cap: Optional[cv2.VideoCapture] = None
        self._latest_frame: Optional[cv2.typing.MatLike] = None
        self._latest_timestamp: float = 0.0
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def open(self) -> bool:
        """
        Open the camera. Returns True on success.
        Tries DirectShow backend first, falls back to default on failure.
        """
        backend = cv2.CAP_DSHOW if self.config.use_dshow else cv2.CAP_ANY

        logger.info(
            f"Opening camera {self.config.camera_index} "
            f"({'DirectShow' if self.config.use_dshow else 'default'} backend)"
        )

        self._cap = cv2.VideoCapture(self.config.camera_index, backend)

        if not self._cap.isOpened():
            logger.warning("DirectShow backend failed, trying default backend")
            self._cap = cv2.VideoCapture(self.config.camera_index)

        if not self._cap.isOpened():
            logger.error(f"Failed to open camera {self.config.camera_index}")
            return False

        # Configure camera properties
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.config.fps)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, self.config.buffer_size)

        # Read back actual properties
        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self._cap.get(cv2.CAP_PROP_FPS)

        logger.info(
            f"Camera opened: {actual_w}x{actual_h} @ {actual_fps} FPS "
            f"(requested {self.config.width}x{self.config.height} @ {self.config.fps})"
        )
        return True

    def start(self) -> bool:
        """Start the capture thread. Returns True if camera opened successfully."""
        if not self.open():
            return False
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="CameraCapture")
        self._thread.start()
        logger.info("Camera capture thread started")
        return True

    def _capture_loop(self):
        """
        Internal capture loop running in a dedicated thread.
        Continuously captures frames and stores only the latest.
        Uses grab() + retrieve() pattern for lower overhead than read().
        """
        last_time = time.monotonic()

        while self._running:
            t0 = time.monotonic()

            # grab() decodes faster and doesn't decode — used to skip stale frames
            grabbed = self._cap.grab()
            if not grabbed:
                logger.warning("Frame grab failed")
                self.metrics.update(time.monotonic() - t0, dropped=True)
                continue

            # retrieve() does the actual decode
            ret, frame = self._cap.retrieve()
            if not ret or frame is None:
                logger.warning("Frame retrieve failed")
                self.metrics.update(time.monotonic() - t0, dropped=True)
                continue

            if self.config.flip_horizontal:
                frame = cv2.flip(frame, 1)

            t1 = time.monotonic()
            elapsed = t1 - last_time
            last_time = t1

            with self._lock:
                self._latest_frame = frame
                self._latest_timestamp = t1

            self.metrics.update(elapsed)

    def get_frame(self) -> Tuple[Optional[cv2.typing.MatLike], float]:
        """
        Get the latest available frame and its timestamp.
        Returns (None, 0.0) if no frame is available yet.
        This method is non-blocking and thread-safe.
        """
        with self._lock:
            return self._latest_frame, self._latest_timestamp

    def stop(self):
        """Stop the capture thread and release the camera."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
        logger.info("Camera capture stopped")

    def get_camera_info(self) -> dict:
        """Return camera properties dictionary."""
        if not self._cap or not self._cap.isOpened():
            return {}
        return {
            "index": self.config.camera_index,
            "width": int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": self._cap.get(cv2.CAP_PROP_FPS),
            "backend": "DirectShow" if self.config.use_dshow else "default",
        }

    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()


def detect_cameras(max_index: int = 4) -> list[dict]:
    """
    Detect available cameras on the system.
    Returns a list of camera info dicts.
    """
    cameras = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            info = {
                "index": i,
                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": cap.get(cv2.CAP_PROP_FPS),
            }
            cameras.append(info)
            cap.release()
    return cameras
