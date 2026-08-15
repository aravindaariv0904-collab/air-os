"""
AirOS Engine — Windows Screenshot Service
Captures real screen content and verifies the resulting file.

Capture targets:
  - active monitor (monitor under the cursor)
  - primary monitor
  - all monitors (full virtual desktop)

Verification pipeline (no fake success):
  capture -> file exists -> size > 0 -> image decodes -> success event
"""

import os
import time
import logging
import threading
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


def get_screenshots_dir() -> str:
    pictures = os.path.join(os.path.expanduser("~"), "Pictures", "AirOS", "Screenshots")
    os.makedirs(pictures, exist_ok=True)
    return pictures


def default_screenshot_path() -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]
    return os.path.join(get_screenshots_dir(), f"AirOS_{ts}.png")


def verify_image_file(path: str) -> tuple:
    """
    Verify a screenshot file is valid.
    Returns (ok, reason).
    """
    if not os.path.exists(path):
        return False, "file_missing"
    try:
        size = os.path.getsize(path)
    except OSError:
        return False, "stat_failed"
    if size <= 0:
        return False, "empty_file"
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.verify()
        return True, "ok"
    except Exception:
        return False, "decode_failed"


@dataclass
class ScreenshotResult:
    ok: bool = False
    path: str = ""
    reason: str = ""
    size_bytes: int = 0
    target: str = "active"


class WindowsScreenshotService:
    """
    Real screen capture using Pillow (GDI). Runs on a worker thread so the
    real-time loop is never blocked by a screen grab.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._last_result: Optional[ScreenshotResult] = None

    def _active_monitor_bbox(self):
        """Bounding box of the monitor under the cursor."""
        try:
            import win32api
            import win32con
            cursor = win32api.GetCursorPos()
            monitors = win32api.EnumDisplayMonitors()
            for hmon, hdc, rect in monitors:
                l, t, r, b = rect
                if l <= cursor[0] < r and t <= cursor[1] < b:
                    return (l, t, r, b)
            return None
        except Exception:
            return None

    def capture(
        self,
        target: str = "active",
        path: Optional[str] = None,
    ) -> ScreenshotResult:
        """
        Capture the screen to a PNG file and verify it.
        target: 'active' | 'primary' | 'all'
        """
        from PIL import ImageGrab

        bbox = None
        if target == "active":
            bbox = self._active_monitor_bbox() or None
        elif target == "primary":
            try:
                import win32api
                bbox = win32api.EnumDisplayMonitors()[0][2]
            except Exception:
                bbox = None

        out_path = path or default_screenshot_path()
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        try:
            try:
                if target == "all":
                    image = ImageGrab.grab(all_screens=True)
                else:
                    image = ImageGrab.grab(bbox=bbox, all_screens=True)
            except Exception:
                image = ImageGrab.grab()
            image.save(out_path, format="PNG")
            image.close()
        except Exception as e:
            logger.error(f"Screenshot capture failed: {e}")
            result = ScreenshotResult(ok=False, path=out_path, reason=f"capture_error: {e}", target=target)
            with self._lock:
                self._last_result = result
            return result

        ok, reason = verify_image_file(out_path)
        size = os.path.getsize(out_path) if ok else 0
        result = ScreenshotResult(
            ok=ok,
            path=out_path,
            reason=reason,
            size_bytes=size,
            target=target,
        )
        with self._lock:
            self._last_result = result
        if ok:
            logger.info(f"Screenshot saved & verified: {out_path} ({size} bytes)")
        else:
            logger.warning(f"Screenshot verification failed: {reason} ({out_path})")
        return result

    def capture_async(self, target: str = "active", callback=None) -> None:
        """Capture on a background thread (never blocks the real-time loop)."""
        def _worker():
            try:
                result = self.capture(target=target)
                if callback:
                    callback(result)
            except Exception as e:
                logger.error(f"Async screenshot error: {e}")

        t = threading.Thread(target=_worker, daemon=True, name="ScreenshotWorker")
        t.start()

    @property
    def last_result(self) -> Optional[ScreenshotResult]:
        with self._lock:
            return self._last_result
