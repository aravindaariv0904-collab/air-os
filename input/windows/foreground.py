"""
AirOS — Foreground App Detector
Detects the currently active (foreground) Windows application by executable name.

Uses ctypes + Win32 GetForegroundWindow / GetWindowThreadProcessId /
QueryFullProcessImageName. Used by the profile manager to auto-switch gesture
profiles based on which app is focused.

Detection is read-only and safe — it never sends input.
"""

import ctypes
import logging
import os
from ctypes import wintypes

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class ForegroundAppDetector:
    """Returns the executable name of the focused window's process."""

    def get_foreground_process(self) -> str:
        """Return the exe name (lowercased, without path) of the foreground app.

        Returns "" if no foreground window/process can be determined.
        """
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return ""

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            handle = kernel32.OpenProcess(
                0x1000,  # PROCESS_QUERY_LIMITED_INFORMATION
                False,
                pid.value,
            )
            if not handle:
                return ""

            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(len(buf))
                if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                    return os.path.basename(buf.value).lower()
                return ""
            finally:
                kernel32.CloseHandle(handle)
        except Exception as e:
            logger.debug(f"Foreground app detection failed: {e}")
            return ""

    def get_foreground_window_title(self) -> str:
        """Return the title of the foreground window (may be empty)."""
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return ""
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return ""
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception as e:
            logger.debug(f"Foreground title detection failed: {e}")
            return ""
