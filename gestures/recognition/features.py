"""
AirOS — Gesture Recognition Features
Normalizes raw MediaPipe landmarks into translation- and scale-invariant
feature vectors used for template recording and matching.

A gesture is represented as a sequence of feature vectors, one per frame.
Each feature vector is the 21 landmarks flattened to (x, y) pairs, translated
so the wrist is at the origin and scaled by hand size. This makes matching
robust to hand position and distance from the camera.
"""

from typing import List

import numpy as np

from engine.landmarks.geometry import WRIST, MIDDLE_MCP

FEATURE_DIM = 21 * 2  # (x, y) for each of 21 landmarks


def normalize_landmarks(landmarks: np.ndarray) -> np.ndarray:
    """Translate to wrist origin and scale by hand size.

    Args:
        landmarks: (21, 3) array of MediaPipe hand landmarks.

    Returns:
        (21, 2) array of normalized (x, y) coordinates.
    """
    arr = np.asarray(landmarks, dtype=np.float32)
    if arr.ndim == 2 and arr.shape[1] >= 2:
        xy = arr[:, :2]
    else:
        raise ValueError(f"Unexpected landmarks shape: {arr.shape}")

    wrist = xy[WRIST]
    scale = float(np.linalg.norm(xy[MIDDLE_MCP] - wrist))
    if scale < 1e-6:
        scale = 1.0

    normalized = (xy - wrist) / scale
    return normalized.astype(np.float32)


def landmark_frame_to_features(landmarks: np.ndarray) -> np.ndarray:
    """Flatten normalized landmarks into a 1-D feature vector (dim 42)."""
    return normalize_landmarks(landmarks).reshape(-1).astype(np.float32)


def sequence_to_features(frames: List[np.ndarray]) -> np.ndarray:
    """Convert a list of landmark frames into a (T, 42) feature sequence."""
    seq = np.stack([landmark_frame_to_features(f) for f in frames], axis=0)
    return seq.astype(np.float32)


def resample_sequence(seq: np.ndarray, target_len: int) -> np.ndarray:
    """Resample a (T, D) feature sequence to exactly `target_len` frames.

    Uses linear interpolation along the time axis, so recordings of different
    lengths can be compared to the same template.
    """
    t, d = seq.shape
    if t == target_len:
        return seq.copy()
    if t == 0:
        raise ValueError("Cannot resample an empty sequence")
    x_old = np.linspace(0.0, 1.0, t)
    x_new = np.linspace(0.0, 1.0, target_len)
    out = np.zeros((target_len, d), dtype=np.float32)
    for dim in range(d):
        out[:, dim] = np.interp(x_new, x_old, seq[:, dim])
    return out
