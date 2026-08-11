"""
AirOS — Gesture Matcher
Matches a live stream of landmarks against recorded gesture templates.

Uses a sliding window of normalized feature frames. For each template the
window is resampled to the template length and compared with mean L1 distance.
A template fires when its distance stays below a threshold for N consecutive
frames (temporal confirmation, consistent with the rest of AirOS).
"""

import time
from typing import Dict, List, Optional

import numpy as np

from gestures.recognition.features import landmark_frame_to_features, resample_sequence
from gestures.recognition.template import GestureTemplate

# Max frames of landmark history kept for matching (~2.5s at 30fps).
MAX_WINDOW = 75


class GestureMatcher:
    """Sliding-window template matcher for custom gestures."""

    def __init__(self, distance_threshold: float = 0.25,
                 confirm_frames: int = 3,
                 cooldown: float = 1.5):
        self._distance_threshold = distance_threshold
        self._confirm_frames = confirm_frames
        self._cooldown = cooldown
        self._window: List[np.ndarray] = []
        self._confirm: Dict[str, int] = {}
        self._last_fire: Dict[str, float] = {}
        self._templates: Dict[str, GestureTemplate] = {}

    # ── Template management ──────────────────────────────────────────
    def add_template(self, template: GestureTemplate):
        self._templates[template.id] = template
        self._confirm[template.id] = 0
        self._last_fire[template.id] = 0.0

    def remove_template(self, template_id: str) -> bool:
        if template_id not in self._templates:
            return False
        del self._templates[template_id]
        self._confirm.pop(template_id, None)
        self._last_fire.pop(template_id, None)
        return True

    def clear_templates(self):
        self._templates.clear()
        self._confirm.clear()
        self._last_fire.clear()

    @property
    def template_ids(self) -> List[str]:
        return list(self._templates.keys())

    # ── Matching ──────────────────────────────────────────────────────
    def update(self, landmarks: np.ndarray, timestamp: float) -> Optional[str]:
        """Feed one frame of landmarks. Returns the matched template id,
        or None."""
        if not self._templates:
            return None

        feat = landmark_frame_to_features(landmarks)
        self._window.append(feat)
        if len(self._window) > MAX_WINDOW:
            self._window.pop(0)

        if len(self._window) < 2:
            return None

        for tid, template in self._templates.items():
            if timestamp - self._last_fire[tid] < self._cooldown:
                continue

            distance = self._match_distance(template)
            if distance <= self._distance_threshold:
                self._confirm[tid] += 1
                if self._confirm[tid] >= self._confirm_frames:
                    self._confirm[tid] = 0
                    self._last_fire[tid] = timestamp
                    return tid
            else:
                self._confirm[tid] = max(0, self._confirm[tid] - 1)

        return None

    def _match_distance(self, template: GestureTemplate) -> float:
        """Mean L1 distance between the tail of the live window and the template.

        Only compares once the window holds at least as many frames as the
        template; the most recent `template.frame_count` frames are aligned
        directly against the template (both are the same length, so no
        resampling distortion — a partial window cannot produce a false match).
        """
        n_frames = template.frame_count
        if len(self._window) < n_frames:
            return float("inf")

        window = np.stack(self._window, axis=0)  # (W, 42)
        tail = window[-n_frames:]                # (n_frames, 42)
        tmpl = template.frames                   # (n_frames, 42)
        diff = np.abs(tail - tmpl)
        per_frame = np.mean(diff, axis=1)
        return float(np.mean(per_frame))

    def reset(self):
        self._window = []
        self._confirm = {tid: 0 for tid in self._templates}

    def get_match_confidence(self, template_id: str) -> float:
        """Inverted confidence: 1.0 when distance is 0, 0.0 at threshold."""
        if template_id not in self._templates:
            return 0.0
        template = self._templates[template_id]
        distance = self._match_distance(template)
        return float(max(0.0, min(1.0, 1.0 - distance / self._distance_threshold)))
