"""
AirOS Engine — Real Latency Instrumentation
Tracks stage-by-stage pipeline timing per frame:
  camera_capture_timestamp
      ↓
  frame_submit_timestamp
      ↓
  tracking_result_timestamp
      ↓
  landmark_processing_timestamp
      ↓
  gesture_timestamp
      ↓
  state_machine_timestamp
      ↓
  input_injection_timestamp

Calculates P50, P95, and P99 percentiles across a rolling window.
"""

import time
import logging
from dataclasses import dataclass, field
from collections import deque
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class StageTimestamps:
    """Timestamps (time.monotonic()) recorded at each pipeline stage for a single frame."""
    frame_id: int = 0
    capture_ts: float = 0.0
    submit_ts: float = 0.0
    tracking_result_ts: float = 0.0
    landmark_ts: float = 0.0
    gesture_ts: float = 0.0
    state_ts: float = 0.0
    input_ts: float = 0.0


@dataclass
class LatencyBreakdown:
    """Stage duration breakdown in milliseconds."""
    capture_ms: float = 0.0
    tracking_ms: float = 0.0
    landmark_ms: float = 0.0
    gesture_ms: float = 0.0
    state_ms: float = 0.0
    input_ms: float = 0.0
    pipeline_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "capture_ms": round(self.capture_ms, 2),
            "tracking_ms": round(self.tracking_ms, 2),
            "landmark_ms": round(self.landmark_ms, 2),
            "gesture_ms": round(self.gesture_ms, 2),
            "state_ms": round(self.state_ms, 2),
            "input_ms": round(self.input_ms, 2),
            "pipeline_ms": round(self.pipeline_ms, 2),
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
        }


class LatencyTracker:
    """
    Rolling window latency analyzer for end-to-end telemetry instrumentation.
    """

    def __init__(self, window_size: int = 120):
        self.window_size = window_size
        self._samples: deque[float] = deque(maxlen=window_size)
        self._last_breakdown = LatencyBreakdown()

    def record_frame(self, ts: StageTimestamps) -> LatencyBreakdown:
        """
        Compute latency breakdown from frame stage timestamps.
        """
        capture_ms = (ts.submit_ts - ts.capture_ts) * 1000.0 if (ts.submit_ts > 0 and ts.capture_ts > 0) else 0.0
        tracking_ms = (ts.tracking_result_ts - ts.submit_ts) * 1000.0 if (ts.tracking_result_ts > 0 and ts.submit_ts > 0) else 0.0
        landmark_ms = (ts.landmark_ts - ts.tracking_result_ts) * 1000.0 if (ts.landmark_ts > 0 and ts.tracking_result_ts > 0) else 0.0
        gesture_ms = (ts.gesture_ts - ts.landmark_ts) * 1000.0 if (ts.gesture_ts > 0 and ts.landmark_ts > 0) else 0.0
        state_ms = (ts.state_ts - ts.gesture_ts) * 1000.0 if (ts.state_ts > 0 and ts.gesture_ts > 0) else 0.0
        input_ms = (ts.input_ts - ts.state_ts) * 1000.0 if (ts.input_ts > 0 and ts.state_ts > 0) else 0.0

        # True end-to-end latency: from camera capture to input injection
        end_ts = ts.input_ts if ts.input_ts > 0 else (ts.state_ts if ts.state_ts > 0 else ts.gesture_ts)
        pipeline_ms = (end_ts - ts.capture_ts) * 1000.0 if (end_ts > 0 and ts.capture_ts > 0) else 0.0

        if pipeline_ms > 0:
            self._samples.append(pipeline_ms)

        p50, p95, p99 = self._compute_percentiles()

        self._last_breakdown = LatencyBreakdown(
            capture_ms=max(0.0, capture_ms),
            tracking_ms=max(0.0, tracking_ms),
            landmark_ms=max(0.0, landmark_ms),
            gesture_ms=max(0.0, gesture_ms),
            state_ms=max(0.0, state_ms),
            input_ms=max(0.0, input_ms),
            pipeline_ms=max(0.0, pipeline_ms),
            p50_ms=p50,
            p95_ms=p95,
            p99_ms=p99,
        )
        return self._last_breakdown

    def _compute_percentiles(self) -> tuple[float, float, float]:
        if not self._samples:
            return 0.0, 0.0, 0.0
        arr = np.array(self._samples)
        p50 = float(np.percentile(arr, 50))
        p95 = float(np.percentile(arr, 95))
        p99 = float(np.percentile(arr, 99))
        return p50, p95, p99

    @property
    def current_breakdown(self) -> LatencyBreakdown:
        return self._last_breakdown
