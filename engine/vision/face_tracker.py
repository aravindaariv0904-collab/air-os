"""
AirOS Engine — Face Tracker
MediaPipe FaceLandmarker wrapper in LIVE_STREAM mode.

Produces 478-point face landmarks (normalized [0,1]) used for:
  - eye-open/closed state (Eye Aspect Ratio)
  - blink detection
  - face presence

Mirrors the HandTracker architecture: async callback, latest-result storage,
non-blocking submission from the real-time loop.
"""

import os
import time
import threading
import urllib.request
import logging
from dataclasses import dataclass, field
from typing import Optional, List

import numpy as np

logger = logging.getLogger(__name__)

# MediaPipe face landmarker model (official, Apache 2.0)
FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)
FACE_MODEL_FILENAME = "face_landmarker.task"


@dataclass
class FaceTrackingResult:
    """Result from one frame of face tracking."""
    timestamp: float = 0.0
    frame_id: int = 0
    capture_timestamp: float = 0.0
    submit_timestamp: float = 0.0
    result_timestamp: float = 0.0
    num_faces: int = 0
    landmarks: list = field(default_factory=list)   # list of (478, 3) np.ndarray
    inference_time_ms: float = 0.0


@dataclass
class FaceTrackerConfig:
    model_path: str = "assets/models/face_landmarker.task"
    num_faces: int = 1
    min_detection_confidence: float = 0.5
    min_presence_confidence: float = 0.5
    min_tracking_confidence: float = 0.5


def download_model(model_path: str) -> bool:
    """Download the MediaPipe face landmarker model if not present."""
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    if os.path.exists(model_path):
        return True
    logger.info(f"Downloading face landmarker model to {model_path}...")
    try:
        urllib.request.urlretrieve(FACE_MODEL_URL, model_path)
        logger.info("Face landmarker model downloaded")
        return True
    except Exception as e:
        logger.error(f"Failed to download face model: {e}")
        return False


class FaceTracker:
    """
    MediaPipe FaceLandmarker wrapper using LIVE_STREAM running mode.
    """

    def __init__(self, config: Optional[FaceTrackerConfig] = None):
        self.config = config or FaceTrackerConfig()
        self._landmarker = None
        self._latest_result: Optional[FaceTrackingResult] = None
        self._result_lock = threading.Lock()
        self._pending_meta: dict = {}
        self._meta_lock = threading.Lock()
        self._initialized = False

    @property
    def initialized(self) -> bool:
        """True once the face landmarker has been successfully initialized."""
        return self._initialized

    def initialize(self) -> bool:
        """Initialize the face landmarker. Downloads model if needed."""
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision
            import mediapipe as mp
        except ImportError as e:
            logger.error(f"MediaPipe not installed: {e}")
            return False

        from engine.resources import resource_path

        model_path = resource_path(self.config.model_path)
        if not os.path.exists(model_path):
            if not download_model(model_path):
                return False

        logger.info("Initializing MediaPipe FaceLandmarker...")
        try:
            base_options = mp_python.BaseOptions(model_asset_path=model_path)
            options = mp_vision.FaceLandmarkerOptions(
                base_options=base_options,
                running_mode=mp_vision.RunningMode.LIVE_STREAM,
                num_faces=self.config.num_faces,
                min_face_detection_confidence=self.config.min_detection_confidence,
                min_face_presence_confidence=self.config.min_presence_confidence,
                min_tracking_confidence=self.config.min_tracking_confidence,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
                result_callback=self._on_result,
            )
            self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)
            self._initialized = True
            logger.info("FaceLandmarker initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize FaceLandmarker: {e}")
            return False

    def _on_result(self, result, output_image, timestamp_ms: int):
        result_ts = time.monotonic()

        frame_id = 0
        capture_ts = 0.0
        submit_ts = 0.0
        with self._meta_lock:
            if timestamp_ms in self._pending_meta:
                frame_id, capture_ts, submit_ts = self._pending_meta.pop(timestamp_ms)
                if len(self._pending_meta) > 100:
                    stale = [k for k in self._pending_meta.keys() if k < timestamp_ms - 1000]
                    for k in stale:
                        self._pending_meta.pop(k, None)

        inference_time = (result_ts - (submit_ts if submit_ts > 0 else result_ts)) * 1000

        tracking_result = FaceTrackingResult(
            timestamp=timestamp_ms / 1000.0,
            frame_id=frame_id,
            capture_timestamp=capture_ts,
            submit_timestamp=submit_ts,
            result_timestamp=result_ts,
            num_faces=len(result.face_landmarks),
            inference_time_ms=inference_time,
        )

        for face_landmarks in result.face_landmarks:
            landmarks_array = np.array(
                [[lm.x, lm.y, lm.z] for lm in face_landmarks],
                dtype=np.float32,
            )
            tracking_result.landmarks.append(landmarks_array)

        with self._result_lock:
            self._latest_result = tracking_result

    def process_frame(
        self,
        frame_bgr,
        timestamp_ms: int,
        frame_id: int = 0,
        capture_timestamp: float = 0.0,
    ):
        """Submit a frame for async inference. Non-blocking."""
        if not self._initialized or self._landmarker is None:
            return

        submit_ts = time.monotonic()
        with self._meta_lock:
            self._pending_meta[timestamp_ms] = (frame_id, capture_timestamp, submit_ts)

        try:
            import mediapipe as mp
            frame_rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
            mp_image = mp.Image(mp.ImageFormat.SRGB, frame_rgb)
            self._landmarker.detect_async(mp_image, timestamp_ms)
        except Exception as e:
            logger.error(f"Face tracker error: {e}")

    def get_latest_result(self) -> Optional[FaceTrackingResult]:
        with self._result_lock:
            return self._latest_result

    def close(self):
        if self._landmarker:
            try:
                self._landmarker.close()
            except Exception:
                pass
            self._landmarker = None
            self._initialized = False
        logger.info("FaceTracker closed")


# MediaPipe face mesh landmarks for the eyes (per eye, 6 points)
LEFT_EYE = (33, 160, 158, 133, 153, 144)
RIGHT_EYE = (362, 385, 387, 263, 373, 380)


def eye_aspect_ratio(landmarks: np.ndarray, eye: tuple) -> float:
    """
    Compute the Eye Aspect Ratio for one eye.
    EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    """
    try:
        p1 = landmarks[eye[0]][:2]
        p2 = landmarks[eye[1]][:2]
        p3 = landmarks[eye[2]][:2]
        p4 = landmarks[eye[3]][:2]
        p5 = landmarks[eye[4]][:2]
        p6 = landmarks[eye[5]][:2]
        a = np.linalg.norm(p2 - p6)
        b = np.linalg.norm(p3 - p5)
        c = np.linalg.norm(p1 - p4)
        if c < 1e-6:
            return 0.0
        return float((a + b) / (2.0 * c))
    except Exception:
        return 0.0


def compute_face_ear(landmarks: np.ndarray) -> float:
    """Mean EAR of both eyes from a single face's landmarks."""
    if landmarks is None or len(landmarks) < 468:
        return 1.0  # no face -> eyes considered open (EAR high)
    return float(
        (eye_aspect_ratio(landmarks, LEFT_EYE) + eye_aspect_ratio(landmarks, RIGHT_EYE)) / 2.0
    )
