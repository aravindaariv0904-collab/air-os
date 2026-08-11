"""
AirOS Engine — One Euro Filter
Adaptive low-pass filter designed for human motion input.
Reference: Casiez, Roussel, Vogel (2012). "1€ Filter: A Simple Speed-based
Low-pass Filter for Noisy Input in Interactive Systems."

License: MIT (original algorithm is freely reusable)

Usage:
    f = OneEuroFilter(freq=30.0, min_cutoff=1.0, beta=0.007, d_cutoff=1.0)
    smooth_x = f(raw_x)  # Call each frame with new value
"""

import math
import time
from typing import Optional


class LowPassFilter:
    """Simple first-order low-pass filter."""

    def __init__(self, cutoff: float, freq: float):
        self._alpha = self._compute_alpha(cutoff, freq)
        self._x: Optional[float] = None
        self._dx: Optional[float] = None

    def _compute_alpha(self, cutoff: float, freq: float) -> float:
        te = 1.0 / freq
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / te)

    def set_params(self, cutoff: float, freq: float):
        self._alpha = self._compute_alpha(cutoff, freq)

    def __call__(self, x: float, alpha: Optional[float] = None) -> float:
        if alpha is None:
            alpha = self._alpha
        if self._x is None:
            self._x = x
        self._x = alpha * x + (1.0 - alpha) * self._x
        return self._x

    @property
    def last_value(self) -> Optional[float]:
        return self._x


class OneEuroFilter:
    """
    One Euro Filter for smooth, low-latency signal filtering.
    
    Parameters:
        freq: Sampling frequency (e.g., 30.0 for 30 FPS)
        min_cutoff: Minimum cutoff frequency. Lower = smoother when still.
                    Start with 1.0, decrease if jitter is still visible.
        beta: Speed coefficient. Higher = more responsive when fast.
              Start with 0.007, increase if lag is too noticeable.
        d_cutoff: Cutoff for derivative filter (default 1.0 Hz is usually fine).
    """

    def __init__(
        self,
        freq: float = 30.0,
        min_cutoff: float = 1.0,
        beta: float = 0.007,
        d_cutoff: float = 1.0,
    ):
        self._freq = freq
        self._min_cutoff = min_cutoff
        self._beta = beta
        self._d_cutoff = d_cutoff
        self._x_filter = LowPassFilter(min_cutoff, freq)
        self._dx_filter = LowPassFilter(d_cutoff, freq)
        self._last_time: Optional[float] = None
        self._last_x: Optional[float] = None

    def __call__(self, x: float, timestamp: Optional[float] = None) -> float:
        """
        Filter a new input value.
        
        Args:
            x: New raw value.
            timestamp: Optional timestamp in seconds. If None, uses current time.
                       Using actual timestamps handles variable FPS correctly.
        
        Returns:
            Filtered value.
        """
        if timestamp is None:
            timestamp = time.monotonic()

        # Update frequency estimate if we have timing info
        if self._last_time is not None:
            dt = timestamp - self._last_time
            if dt > 0:
                self._freq = 1.0 / dt
        self._last_time = timestamp

        # Estimate speed (derivative)
        if self._last_x is None:
            dx = 0.0
        else:
            dx = (x - self._last_x) * self._freq
        self._last_x = x

        # Filter derivative
        dx_hat = self._dx_filter(dx)

        # Compute adaptive cutoff: faster movement = higher cutoff = less smoothing
        cutoff = self._min_cutoff + self._beta * abs(dx_hat)

        # Update x filter with new cutoff
        self._x_filter.set_params(cutoff, self._freq)

        return self._x_filter(x)

    def reset(self):
        """Reset filter state. Call if tracking is lost and resumes."""
        self._x_filter._x = None
        self._dx_filter._x = None
        self._last_time = None
        self._last_x = None


class OneEuroFilter2D:
    """
    Two-dimensional One Euro Filter for cursor (X, Y) positions.
    Each axis is filtered independently.
    """

    def __init__(
        self,
        freq: float = 30.0,
        min_cutoff: float = 1.0,
        beta: float = 0.007,
        d_cutoff: float = 1.0,
    ):
        self.x_filter = OneEuroFilter(freq, min_cutoff, beta, d_cutoff)
        self.y_filter = OneEuroFilter(freq, min_cutoff, beta, d_cutoff)

    def __call__(
        self, x: float, y: float, timestamp: Optional[float] = None
    ) -> tuple[float, float]:
        """Filter (x, y) pair. Returns (filtered_x, filtered_y)."""
        return (
            self.x_filter(x, timestamp),
            self.y_filter(y, timestamp),
        )

    def reset(self):
        """Reset both filters."""
        self.x_filter.reset()
        self.y_filter.reset()
