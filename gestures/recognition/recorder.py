"""
AirOS — Gesture Recorder
Captures a live gesture as the user performs it, then produces a normalized
template for the Gesture Studio.

Recording workflow:
  recorder = GestureRecorder()
  recorder.start()
  recorder.add_frame(landmarks)   # called every pipeline frame
  template = recorder.finish("My Gesture")   # resampled to fixed length
"""

import time
from typing import Optional

import numpy as np

from gestures.recognition.features import landmark_frame_to_features, resample_sequence
from gestures.recognition.template import GestureTemplate

# Fixed internal template length: recordings are resampled to this many frames.
DEFAULT_TEMPLATE_FRAMES = 30


class GestureRecorder:
    """Buffers landmark frames and produces a GestureTemplate."""

    def __init__(self, target_frames: int = DEFAULT_TEMPLATE_FRAMES):
        self._target_frames = target_frames
        self._buffer: list = []
        self._started_at: Optional[float] = None
        self._recording = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def frame_count(self) -> int:
        return len(self._buffer)

    @property
    def elapsed(self) -> float:
        if self._started_at is None:
            return 0.0
        return time.monotonic() - self._started_at

    def start(self):
        """Begin a new recording session."""
        self._buffer = []
        self._started_at = time.monotonic()
        self._recording = True

    def add_frame(self, landmarks: np.ndarray) -> bool:
        """Append a normalized frame. Returns True if accepted."""
        if not self._recording:
            return False
        feat = landmark_frame_to_features(landmarks)
        self._buffer.append(feat)
        return True

    def finish(self, name: str, gesture_id: Optional[str] = None,
               description: str = "") -> Optional[GestureTemplate]:
        """Stop recording and produce a template. Returns None if too short."""
        if not self._recording:
            return None
        self._recording = False
        if len(self._buffer) < 2:
            return None

        seq = np.stack(self._buffer, axis=0).astype(np.float32)
        seq = resample_sequence(seq, self._target_frames)
        return GestureTemplate.from_frames(
            name=name,
            frames=seq,
            gesture_id=gesture_id,
            description=description,
        )

    def cancel(self):
        """Abort the current recording session."""
        self._recording = False
        self._buffer = []
        self._started_at = None
