"""
AirOS — Gesture Template
A recorded custom gesture: a time-series of normalized feature vectors plus
metadata. Templates are persisted as JSON (frames as a flat list).
"""

from __future__ import annotations

import time
import json
import itertools
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from gestures.recognition.features import FEATURE_DIM

_id_counter = itertools.count()


@dataclass
class GestureTemplate:
    """A recorded custom gesture template."""
    id: str
    name: str
    frames: np.ndarray                # (T, 42) normalized feature sequence
    created_at: float = field(default_factory=time.time)
    description: str = ""
    action: str = "left_click"        # action name from the safe vocabulary

    @property
    def frame_count(self) -> int:
        return int(self.frames.shape[0])

    @property
    def duration_s(self) -> float:
        return self.frame_count / 30.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "description": self.description,
            "action": self.action,
            "frame_count": self.frame_count,
            "duration_s": round(self.duration_s, 3),
            "frames": self.frames.reshape(-1).astype(float).tolist(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GestureTemplate":
        frames = np.asarray(d["frames"], dtype=np.float32)
        n = frames.size // FEATURE_DIM
        frames = frames.reshape(n, FEATURE_DIM)
        return cls(
            id=d["id"],
            name=d["name"],
            frames=frames,
            created_at=d.get("created_at", time.time()),
            description=d.get("description", ""),
            action=d.get("action", "left_click"),
        )

    @classmethod
    def from_frames(cls, name: str, frames: np.ndarray,
                    gesture_id: Optional[str] = None,
                    description: str = "",
                    action: str = "left_click") -> "GestureTemplate":
        """Build a template from a (T, 42) feature sequence."""
        return cls(
            id=gesture_id or f"custom_{int(time.time() * 1000)}_{next(_id_counter)}",
            name=name,
            frames=np.asarray(frames, dtype=np.float32),
            description=description,
            action=action,
        )


def templates_to_json(templates: List[GestureTemplate]) -> str:
    return json.dumps(
        {"version": "1.0", "templates": [t.to_dict() for t in templates]},
        indent=2,
    )


def templates_from_json(text: str) -> List[GestureTemplate]:
    data = json.loads(text)
    return [GestureTemplate.from_dict(t) for t in data.get("templates", [])]
