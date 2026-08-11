"""
AirOS Engine — Cursor Engine
Maps normalized camera coordinates [0,1] to screen pixel coordinates.

Pipeline:
  Camera coords [0,1]
    ↓ Interaction region clamp
    ↓ Normalize within interaction region
    ↓ Dead zone filter (suppress micro-tremor)
    ↓ One Euro Filter (adaptive smoothing)
    ↓ Screen space mapping
    ↓ SendInput

Design goals:
- Slow movement = high precision (low cutoff, heavily smoothed)
- Fast movement = high responsiveness (high cutoff, less smoothed)
- Stationary hand = cursor stays still (dead zone)
"""

import time
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from engine.filtering.one_euro import OneEuroFilter2D

logger = logging.getLogger(__name__)


@dataclass
class CursorConfig:
    """Cursor engine configuration."""
    # Interaction region: fraction of frame [0,1] used as the active area
    # e.g., region_margin = 0.15 means only the middle 70% of the frame is used
    region_left: float = 0.10
    region_right: float = 0.90
    region_top: float = 0.10
    region_bottom: float = 0.85

    # Dead zone: ignore movement smaller than this (normalized units after region)
    dead_zone: float = 0.008

    # Screen dimensions (will be auto-detected if 0)
    screen_width: int = 0
    screen_height: int = 0

    # One Euro Filter parameters
    one_euro_freq: float = 30.0
    one_euro_min_cutoff: float = 1.2     # Stability when still
    one_euro_beta: float = 0.008         # Responsiveness when fast
    one_euro_d_cutoff: float = 1.0

    # Sensitivity multiplier (1.0 = 1:1 mapping, >1.0 = faster)
    sensitivity: float = 1.0


@dataclass
class CursorState:
    """Current cursor state."""
    screen_x: int = 0
    screen_y: int = 0
    raw_norm_x: float = 0.0    # After region normalization, before dead zone
    raw_norm_y: float = 0.0
    filtered_x: float = 0.0    # After One Euro Filter
    filtered_y: float = 0.0
    in_dead_zone: bool = False


class CursorEngine:
    """
    Maps normalized landmark positions to Windows screen coordinates.
    
    Usage:
        engine = CursorEngine(config)
        engine.initialize()  # Auto-detects screen size
        
        # Each frame:
        screen_x, screen_y = engine.update(norm_x, norm_y)
        adapter.move_cursor(screen_x, screen_y)
    """

    def __init__(self, config: Optional[CursorConfig] = None):
        self.config = config or CursorConfig()
        self._filter = OneEuroFilter2D(
            freq=self.config.one_euro_freq,
            min_cutoff=self.config.one_euro_min_cutoff,
            beta=self.config.one_euro_beta,
            d_cutoff=self.config.one_euro_d_cutoff,
        )
        self._state = CursorState()
        self._last_screen_x: int = 0
        self._last_screen_y: int = 0

    def initialize(self) -> bool:
        """Auto-detect screen dimensions if not configured."""
        if self.config.screen_width == 0 or self.config.screen_height == 0:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                # Use virtual screen for multi-monitor support
                self.config.screen_width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
                self.config.screen_height = user32.GetSystemMetrics(79) # SM_CYVIRTUALSCREEN
                if self.config.screen_width == 0:
                    self.config.screen_width = user32.GetSystemMetrics(0)   # SM_CXSCREEN
                    self.config.screen_height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
            except Exception as e:
                logger.warning(f"Could not detect screen size: {e}. Using 1920x1080")
                self.config.screen_width = 1920
                self.config.screen_height = 1080

        logger.info(
            f"CursorEngine initialized: screen={self.config.screen_width}x{self.config.screen_height}, "
            f"region=({self.config.region_left:.2f},{self.config.region_top:.2f})"
            f"-({self.config.region_right:.2f},{self.config.region_bottom:.2f})"
        )
        return True

    def update(
        self,
        norm_x: float,
        norm_y: float,
        timestamp: Optional[float] = None,
    ) -> Tuple[int, int]:
        """
        Convert normalized camera position to screen pixel coordinates.
        
        Args:
            norm_x, norm_y: Normalized position [0,1] from MediaPipe landmarks
            timestamp: Optional monotonic timestamp for filter
        
        Returns:
            (screen_x, screen_y) in pixels, clamped to screen bounds
        """
        if timestamp is None:
            timestamp = time.monotonic()

        # 1. Clamp to interaction region
        region_x = self._normalize_to_region(
            norm_x, self.config.region_left, self.config.region_right
        )
        region_y = self._normalize_to_region(
            norm_y, self.config.region_top, self.config.region_bottom
        )
        self._state.raw_norm_x = region_x
        self._state.raw_norm_y = region_y

        # 2. Dead zone check
        if self._is_in_dead_zone(region_x, region_y):
            self._state.in_dead_zone = True
            # Return last stable position
            return self._last_screen_x, self._last_screen_y

        self._state.in_dead_zone = False

        # 3. Apply One Euro Filter
        filtered_x, filtered_y = self._filter(region_x, region_y, timestamp)
        self._state.filtered_x = filtered_x
        self._state.filtered_y = filtered_y

        # 4. Apply sensitivity and map to screen pixels
        screen_x = int(filtered_x * self.config.screen_width * self.config.sensitivity)
        screen_y = int(filtered_y * self.config.screen_height * self.config.sensitivity)

        # 5. Clamp to screen bounds
        screen_x = max(0, min(self.config.screen_width - 1, screen_x))
        screen_y = max(0, min(self.config.screen_height - 1, screen_y))

        self._state.screen_x = screen_x
        self._state.screen_y = screen_y
        self._last_screen_x = screen_x
        self._last_screen_y = screen_y

        return screen_x, screen_y

    def _normalize_to_region(self, value: float, region_min: float, region_max: float) -> float:
        """
        Normalize a value within the interaction region [region_min, region_max] → [0, 1].
        Values outside the region are clamped.
        """
        if region_max <= region_min:
            return 0.5
        normalized = (value - region_min) / (region_max - region_min)
        return max(0.0, min(1.0, normalized))

    def _is_in_dead_zone(self, x: float, y: float) -> bool:
        """
        Returns True if movement from last position is below dead zone threshold.
        Dead zone is in normalized (post-region) space.
        """
        if self._state.filtered_x == 0.0 and self._state.filtered_y == 0.0:
            return False  # No previous position
        dx = abs(x - self._state.filtered_x)
        dy = abs(y - self._state.filtered_y)
        return (dx < self.config.dead_zone) and (dy < self.config.dead_zone)

    def reset_filter(self):
        """Reset the filter when tracking is lost/resumed."""
        self._filter.reset()

    def get_state(self) -> CursorState:
        return self._state

    def update_config(self, **kwargs):
        """Update cursor configuration at runtime."""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.debug(f"CursorEngine config: {key} = {value}")
