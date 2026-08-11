"""
AirOS Engine — Hand Tracker
MediaPipe HandLandmarker wrapper with LIVE_STREAM mode.

Architecture notes:
- Uses MediaPipe Tasks API (not legacy mp.solutions.hands)
- LIVE_STREAM mode: async callback — does NOT block the main loop
- Measures inference time separately from capture time
- Downloads model file if not present
"""

import os
import time
import logging
import threading
import urllib.request
from dataclasses import dataclass, field
from typing import Optional, Callable, List

import numpy as np

logger = logging.getLogger(__name__)

# MediaPipe model download URL (official)
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
MODEL_FILENAME = "hand_landmarker.task"


@dataclass
class HandTrackingResult:
    """Result from one frame of hand tracking."""
    timestamp: float = 0.0
    num_hands: int = 0
    landmarks: list = field(default_factory=list)       # List of (21, 3) np.ndarray
    handedness: list = field(default_factory=list)       # List of "Left"/"Right"
    inference_time_ms: float = 0.0


@dataclass
class TrackerConfig:
    model_path: str = "assets/models/hand_landmarker.task"
    num_hands: int = 2
    min_detection_confidence: float = 0.6
    min_presence_confidence: float = 0.6
    min_tracking_confidence: float = 0.6


def download_model(model_path: str) -> bool:
    """Download the MediaPipe hand landmarker model if not present."""
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    if os.path.exists(model_path):
        logger.info(f"Model already exists: {model_path}")
        return True

    logger.info(f"Downloading MediaPipe model to {model_path}...")
    logger.info(f"URL: {MODEL_URL}")
    try:
        urllib.request.urlretrieve(MODEL_URL, model_path)
        logger.info("Model downloaded successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to download model: {e}")
        return False


class HandTracker:
    """
    MediaPipe HandLandmarker wrapper using LIVE_STREAM running mode.
    
    LIVE_STREAM mode:
    - Never blocks the calling thread.
    - Results arrive via async callback.
    - Always processes the LATEST frame submitted.
    - If a frame arrives while inference is running, it is queued internally.
    
    Usage:
        tracker = HandTracker(config)
        tracker.initialize()
        
        # In your main loop:
        tracker.process_frame(frame, timestamp_ms)
        
        # Get latest result (may be from a previous frame):
        result = tracker.get_latest_result()
    """

    def __init__(self, config: Optional[TrackerConfig] = None):
        self.config = config or TrackerConfig()
        self._landmarker = None
        self._latest_result: Optional[HandTrackingResult] = None
        self._result_lock = threading.Lock()
        self._inference_start: float = 0.0
        self._initialized = False

    def initialize(self) -> bool:
        """
        Initialize the hand landmarker. Downloads model if needed.
        Returns True on success.
        """
        # Import here to avoid import errors if mediapipe not installed
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision
            import mediapipe as mp
        except ImportError as e:
            logger.error(f"MediaPipe not installed: {e}")
            return False

        model_path = self.config.model_path
        if not os.path.exists(model_path):
            if not download_model(model_path):
                return False

        logger.info("Initializing MediaPipe HandLandmarker...")

        try:
            base_options = mp_python.BaseOptions(model_asset_path=model_path)
            options = mp_vision.HandLandmarkerOptions(
                base_options=base_options,
                running_mode=mp_vision.RunningMode.LIVE_STREAM,
                num_hands=self.config.num_hands,
                min_hand_detection_confidence=self.config.min_detection_confidence,
                min_hand_presence_confidence=self.config.min_presence_confidence,
                min_tracking_confidence=self.config.min_tracking_confidence,
                result_callback=self._on_result,
            )
            self._landmarker = mp_vision.HandLandmarker.create_from_options(options)
            self._initialized = True
            logger.info("HandLandmarker initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize HandLandmarker: {e}")
            return False

    def _on_result(self, result, output_image, timestamp_ms: int):
        """
        Async callback from MediaPipe. Called from MediaPipe's internal thread.
        Store the result thread-safely.
        """
        inference_time = (time.monotonic() - self._inference_start) * 1000

        tracking_result = HandTrackingResult(
            timestamp=timestamp_ms / 1000.0,
            num_hands=len(result.hand_landmarks),
            inference_time_ms=inference_time,
        )

        for i, hand_landmarks in enumerate(result.hand_landmarks):
            landmarks_array = np.array(
                [[lm.x, lm.y, lm.z] for lm in hand_landmarks],
                dtype=np.float32
            )
            tracking_result.landmarks.append(landmarks_array)

            # Handedness
            if result.handedness and i < len(result.handedness):
                cat = result.handedness[i][0]
                # Note: MediaPipe reports mirrored handedness for front-facing camera.
                # Since we flip the frame, we need to swap Left/Right.
                side = "Right" if cat.category_name == "Left" else "Left"
                tracking_result.handedness.append(side)
            else:
                tracking_result.handedness.append("Unknown")

        with self._result_lock:
            self._latest_result = tracking_result

    def process_frame(self, frame_bgr, timestamp_ms: int):
        """
        Submit a frame for async inference. Non-blocking.
        
        Args:
            frame_bgr: BGR frame from OpenCV (will be converted to RGB for MediaPipe)
            timestamp_ms: Frame timestamp in milliseconds (must be monotonically increasing)
        """
        if not self._initialized or self._landmarker is None:
            return

        try:
            import mediapipe as mp
            import numpy as np
            # Convert BGR to RGB; must be C-contiguous uint8 for MediaPipe
            frame_rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
            # Use positional args — MediaPipe 0.10.x rejects keyword args here
            mp_image = mp.Image(mp.ImageFormat.SRGB, frame_rgb)
            self._inference_start = time.monotonic()
            self._landmarker.detect_async(mp_image, timestamp_ms)
        except Exception as e:
            logger.error(f"Error processing frame: {e}")

    def get_latest_result(self) -> Optional[HandTrackingResult]:
        """Get the most recent tracking result. Thread-safe. Non-blocking."""
        with self._result_lock:
            return self._latest_result

    def close(self):
        """Release MediaPipe resources."""
        if self._landmarker:
            self._landmarker.close()
            self._landmarker = None
            self._initialized = False
        logger.info("HandTracker closed")
