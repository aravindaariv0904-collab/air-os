"""
AirOS Engine — Geometric Utilities
Fast geometric computations on landmark arrays.
All functions operate on normalized MediaPipe coordinates [0,1].
"""

import math
import numpy as np
from typing import List, Tuple, Optional
from engine.landmarks.definitions import *


def landmark_to_array(landmark) -> np.ndarray:
    """Convert a MediaPipe NormalizedLandmark to a numpy [x, y, z] array."""
    return np.array([landmark.x, landmark.y, landmark.z], dtype=np.float32)


def landmarks_to_array(landmarks) -> np.ndarray:
    """Convert list of 21 MediaPipe landmarks to shape (21, 3) array."""
    return np.array([[lm.x, lm.y, lm.z] for lm in landmarks], dtype=np.float32)


def euclidean_distance_2d(a: np.ndarray, b: np.ndarray) -> float:
    """Euclidean distance in 2D (XY plane only, ignoring Z)."""
    return float(np.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2))


def euclidean_distance_3d(a: np.ndarray, b: np.ndarray) -> float:
    """Euclidean distance in 3D."""
    return float(np.linalg.norm(a - b))


def hand_scale(landmarks: np.ndarray) -> float:
    """
    Estimate hand scale as wrist-to-middle-MCP distance.
    Used to normalize distances (e.g., pinch distance) for varying camera distances.
    Returns a float in [0, 1] normalized coordinates.
    """
    wrist = landmarks[WRIST]
    middle_mcp = landmarks[MIDDLE_MCP]
    scale = euclidean_distance_2d(wrist, middle_mcp)
    # Prevent division by zero
    return max(scale, 1e-6)


def normalized_pinch_distance(landmarks: np.ndarray) -> float:
    """
    Pinch distance between index tip and thumb tip, normalized by hand scale.
    Returns a value in [0, ~2] where ~0.0 = fully pinched, ~1.0 = relaxed.
    """
    index_tip = landmarks[INDEX_TIP]
    thumb_tip = landmarks[THUMB_TIP]
    raw_dist = euclidean_distance_2d(index_tip, thumb_tip)
    scale = hand_scale(landmarks)
    return raw_dist / scale


def is_finger_extended(landmarks: np.ndarray, tip_idx: int, mcp_idx: int) -> bool:
    """
    Returns True if the finger is extended (tip is above MCP in image space).
    Note: In MediaPipe, Y increases downward, so tip.y < mcp.y means extended.
    Uses a small margin to reduce noise.
    """
    tip_y = landmarks[tip_idx][1]
    mcp_y = landmarks[mcp_idx][1]
    # Extended = tip is HIGHER than MCP (lower Y value in image coords)
    return tip_y < (mcp_y - 0.02)  # 0.02 margin to prevent false positives


def count_extended_fingers(landmarks: np.ndarray, include_thumb: bool = False) -> int:
    """Count how many fingers are extended."""
    finger_pairs = [
        (INDEX_TIP, INDEX_MCP),
        (MIDDLE_TIP, MIDDLE_MCP),
        (RING_TIP, RING_MCP),
        (PINKY_TIP, PINKY_MCP),
    ]
    count = sum(1 for tip, mcp in finger_pairs if is_finger_extended(landmarks, tip, mcp))
    if include_thumb:
        # Thumb uses X axis (horizontal extension)
        thumb_tip_x = landmarks[THUMB_TIP][0]
        wrist_x = landmarks[WRIST][0]
        index_mcp_x = landmarks[INDEX_MCP][0]
        # Thumb extended = tip is away from index finger base
        if abs(thumb_tip_x - wrist_x) > abs(index_mcp_x - wrist_x) * 0.5:
            count += 1
    return count


def is_open_palm(landmarks: np.ndarray) -> bool:
    """All four fingers extended (thumb not required for open palm gesture)."""
    finger_pairs = [
        (INDEX_TIP, INDEX_MCP),
        (MIDDLE_TIP, MIDDLE_MCP),
        (RING_TIP, RING_MCP),
        (PINKY_TIP, PINKY_MCP),
    ]
    return all(is_finger_extended(landmarks, tip, mcp) for tip, mcp in finger_pairs)


def is_index_only(landmarks: np.ndarray) -> bool:
    """
    Returns True if ONLY the index finger is extended (pointer gesture).
    Middle, ring, pinky should be curled.
    """
    index_extended = is_finger_extended(landmarks, INDEX_TIP, INDEX_MCP)
    middle_curled = not is_finger_extended(landmarks, MIDDLE_TIP, MIDDLE_MCP)
    ring_curled = not is_finger_extended(landmarks, RING_TIP, RING_MCP)
    pinky_curled = not is_finger_extended(landmarks, PINKY_TIP, PINKY_MCP)
    return index_extended and middle_curled and ring_curled and pinky_curled


def wrist_position(landmarks: np.ndarray) -> np.ndarray:
    """Return wrist [x, y] position (2D only)."""
    return landmarks[WRIST][:2]


def index_tip_position(landmarks: np.ndarray) -> np.ndarray:
    """Return index fingertip [x, y] position."""
    return landmarks[INDEX_TIP][:2]


def hand_center(landmarks: np.ndarray) -> np.ndarray:
    """Return the centroid of all landmarks [x, y]."""
    return np.mean(landmarks[:, :2], axis=0)


def angle_between_vectors(v1: np.ndarray, v2: np.ndarray) -> float:
    """Angle in degrees between two 2D vectors."""
    cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return float(math.degrees(math.acos(cos_angle)))
