"""
AirOS — Calibration System
Guided multi-step calibration for interaction region, sensitivity, and thresholds.
Stores results in config/calibration.json.
"""

import json
import os
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from enum import Enum, auto

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config")
CALIBRATION_FILE = os.path.join(CONFIG_DIR, "calibration.json")


class CalibStep(Enum):
    IDLE = auto()
    CHECK_CAMERA = auto()
    POSITION = auto()
    DETECT_HAND = auto()
    MOVE_LEFT = auto()
    MOVE_RIGHT = auto()
    MOVE_UP = auto()
    MOVE_DOWN = auto()
    PINCH = auto()
    OPEN_PALM = auto()
    TWO_HAND = auto()
    AIR_TAP = auto()
    COMPLETE = auto()


@dataclass
class CalibrationProfile:
    """Stores calibrated interaction parameters."""
    # Interaction region boundaries [0,1] in camera space
    region_left: float = 0.10
    region_right: float = 0.90
    region_top: float = 0.10
    region_bottom: float = 0.85

    # Detected during calibration
    pinch_threshold: float = 0.30
    release_threshold: float = 0.45
    scroll_velocity_threshold: float = 0.15
    swipe_displacement_threshold: float = 0.18
    swipe_velocity_threshold: float = 0.35
    air_tap_threshold: float = 0.04

    # User preferences
    preferred_hand: str = "right"   # "left" or "right"
    sensitivity: float = 1.0
    smoothing_min_cutoff: float = 1.2
    smoothing_beta: float = 0.008

    # Calibration metadata
    calibrated: bool = False
    calibration_date: str = ""
    version: str = "1.0"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CalibrationProfile":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class CalibrationManager:
    """
    Manages the calibration workflow.
    Each step collects data from the real-time pipeline.
    """

    STEP_ORDER = [
        CalibStep.CHECK_CAMERA,
        CalibStep.POSITION,
        CalibStep.DETECT_HAND,
        CalibStep.MOVE_LEFT,
        CalibStep.MOVE_RIGHT,
        CalibStep.MOVE_UP,
        CalibStep.MOVE_DOWN,
        CalibStep.PINCH,
        CalibStep.OPEN_PALM,
        CalibStep.TWO_HAND,
        CalibStep.COMPLETE,
    ]

    STEP_INSTRUCTIONS = {
        CalibStep.CHECK_CAMERA: "Checking camera...",
        CalibStep.POSITION: "Sit at a comfortable distance (50-80cm). Face the camera.",
        CalibStep.DETECT_HAND: "Hold up your hand in front of the camera.",
        CalibStep.MOVE_LEFT: "Slowly move your hand to the LEFT edge of your comfortable range.",
        CalibStep.MOVE_RIGHT: "Slowly move your hand to the RIGHT edge of your comfortable range.",
        CalibStep.MOVE_UP: "Slowly move your hand to the TOP of your comfortable range.",
        CalibStep.MOVE_DOWN: "Slowly move your hand to the BOTTOM of your comfortable range.",
        CalibStep.PINCH: "Pinch your index finger and thumb together, then release. Repeat 3 times.",
        CalibStep.OPEN_PALM: "Open your palm wide and hold for 2 seconds.",
        CalibStep.TWO_HAND: "Hold up BOTH hands.",
        CalibStep.COMPLETE: "Calibration complete!",
    }

    def __init__(self, clock=None):
        self._clock = clock or time.monotonic
        self._profile = CalibrationProfile()
        self._step = CalibStep.IDLE
        self._step_index = 0
        self._step_data: List = []
        self._step_start: float = 0.0
        self._step_timeout: float = 10.0
        self._completed_steps: List[CalibStep] = []
        # Boundary collection
        self._left_samples: List[float] = []
        self._right_samples: List[float] = []
        self._top_samples: List[float] = []
        self._bottom_samples: List[float] = []
        self._pinch_samples: List[float] = []

    def start(self):
        """Begin calibration workflow."""
        self._profile = CalibrationProfile()
        self._step_index = 0
        self._completed_steps = []
        self._left_samples = []
        self._right_samples = []
        self._top_samples = []
        self._bottom_samples = []
        self._pinch_samples = []
        self._advance_step()
        logger.info("Calibration started")

    def _advance_step(self):
        if self._step_index < len(self.STEP_ORDER):
            self._step = self.STEP_ORDER[self._step_index]
            self._step_start = self._clock()
            self._step_index += 1
            logger.info(f"Calibration step: {self._step.name}")

    def update(self, landmarks, num_hands: int, wrist_pos=None, pinch_dist: float = 1.0):
        """
        Called every frame during calibration with current tracking data.
        Returns True when calibration is complete.
        """
        if self._step == CalibStep.IDLE or self._step == CalibStep.COMPLETE:
            return self._step == CalibStep.COMPLETE

        elapsed = self._clock() - self._step_start

        if self._step == CalibStep.CHECK_CAMERA:
            if num_hands >= 0:  # Camera is working
                time.sleep(0.5)
                self._advance_step()

        elif self._step == CalibStep.POSITION:
            if elapsed > 3.0:  # Just wait for user to position
                self._advance_step()

        elif self._step == CalibStep.DETECT_HAND:
            if num_hands > 0:
                self._advance_step()

        elif self._step == CalibStep.MOVE_LEFT:
            if num_hands > 0 and wrist_pos is not None:
                self._left_samples.append(wrist_pos[0])
                if elapsed > 3.0 and len(self._left_samples) >= 30:
                    # Use the leftmost 10th percentile of samples
                    sorted_samples = sorted(self._left_samples)
                    self._profile.region_left = sorted_samples[len(sorted_samples) // 10]
                    self._advance_step()

        elif self._step == CalibStep.MOVE_RIGHT:
            if num_hands > 0 and wrist_pos is not None:
                self._right_samples.append(wrist_pos[0])
                if elapsed > 3.0 and len(self._right_samples) >= 30:
                    sorted_samples = sorted(self._right_samples)
                    self._profile.region_right = sorted_samples[-(len(sorted_samples) // 10)]
                    self._advance_step()

        elif self._step == CalibStep.MOVE_UP:
            if num_hands > 0 and wrist_pos is not None:
                self._top_samples.append(wrist_pos[1])
                if elapsed > 3.0 and len(self._top_samples) >= 30:
                    sorted_samples = sorted(self._top_samples)
                    self._profile.region_top = sorted_samples[len(sorted_samples) // 10]
                    self._advance_step()

        elif self._step == CalibStep.MOVE_DOWN:
            if num_hands > 0 and wrist_pos is not None:
                self._bottom_samples.append(wrist_pos[1])
                if elapsed > 3.0 and len(self._bottom_samples) >= 30:
                    sorted_samples = sorted(self._bottom_samples)
                    self._profile.region_bottom = sorted_samples[-(len(sorted_samples) // 10)]
                    self._advance_step()

        elif self._step == CalibStep.PINCH:
            if num_hands > 0:
                self._pinch_samples.append(pinch_dist)
                if elapsed > 4.0 and len(self._pinch_samples) > 10:
                    min_dist = min(self._pinch_samples)
                    # Set threshold 50% above minimum observed pinch distance
                    self._profile.pinch_threshold = min(min_dist * 1.5, 0.35)
                    self._profile.release_threshold = self._profile.pinch_threshold * 1.5
                    self._advance_step()

        elif self._step in (CalibStep.OPEN_PALM, CalibStep.TWO_HAND, CalibStep.AIR_TAP):
            if elapsed > 3.0:
                self._advance_step()

        # Timeout protection — advance if stuck
        if elapsed > self._step_timeout and self._step not in (CalibStep.COMPLETE, CalibStep.IDLE):
            logger.warning(f"Calibration step {self._step.name} timed out — using defaults")
            self._advance_step()

        if self._step == CalibStep.COMPLETE:
            self._finalize()
            return True

        return False

    def _finalize(self):
        """Save calibration profile."""
        import datetime
        self._profile.calibrated = True
        self._profile.calibration_date = datetime.datetime.now().isoformat()
        self.save()
        logger.info(f"Calibration complete: region=({self._profile.region_left:.2f},{self._profile.region_top:.2f})"
                    f"-({self._profile.region_right:.2f},{self._profile.region_bottom:.2f})")

    def save(self):
        """Save calibration to file."""
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CALIBRATION_FILE, "w") as f:
            json.dump(self._profile.to_dict(), f, indent=2)
        logger.info(f"Calibration saved to {CALIBRATION_FILE}")

    def load(self) -> bool:
        """Load calibration from file. Returns True if loaded."""
        if not os.path.exists(CALIBRATION_FILE):
            return False
        try:
            with open(CALIBRATION_FILE) as f:
                data = json.load(f)
            self._profile = CalibrationProfile.from_dict(data)
            logger.info(f"Calibration loaded from {CALIBRATION_FILE}")
            return True
        except Exception as e:
            logger.warning(f"Failed to load calibration: {e}")
            return False

    @property
    def profile(self) -> CalibrationProfile:
        return self._profile

    @property
    def current_step(self) -> CalibStep:
        return self._step

    @property
    def current_instruction(self) -> str:
        return self.STEP_INSTRUCTIONS.get(self._step, "")

    @property
    def progress_pct(self) -> float:
        return self._step_index / len(self.STEP_ORDER) * 100

    def get_status(self) -> dict:
        return {
            "step": self._step.name,
            "instruction": self.current_instruction,
            "progress": self.progress_pct,
            "calibrated": self._profile.calibrated,
        }

    def skip_to_defaults(self):
        """Skip calibration and use default values."""
        self._profile.calibrated = True
        self._step = CalibStep.COMPLETE
        self.save()
        logger.info("Using default calibration values")
