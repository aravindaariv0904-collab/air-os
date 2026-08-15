"""
AirOS Engine — Desktop Context Service
Tracks real Windows desktop state used for contextual commands:
  - foreground window (handle, title, process)
  - all visible top-level windows (for target resolution like "close the Claude tab")
  - cursor position
  - monitor geometry

Context is refreshed on demand (before contextual commands) and via a
lightweight polling thread.
"""

import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class WindowInfo:
    hwnd: int = 0
    title: str = ""
    process_name: str = ""
    pid: int = 0
    visible: bool = True

    def to_dict(self) -> dict:
        return {
            "hwnd": self.hwnd,
            "title": self.title,
            "process_name": self.process_name,
            "pid": self.pid,
        }


@dataclass
class DesktopContext:
    foreground_hwnd: int = 0
    foreground_title: str = ""
    foreground_process: str = ""
    cursor_x: int = 0
    cursor_y: int = 0
    windows: List[WindowInfo] = field(default_factory=list)
    refreshed_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "foreground": {
                "hwnd": self.foreground_hwnd,
                "title": self.foreground_title,
                "process": self.foreground_process,
            },
            "cursor": {"x": self.cursor_x, "y": self.cursor_y},
            "window_count": len(self.windows),
            "refreshed_at": round(self.refreshed_at, 3),
        }


class DesktopContextService:
    """Authoritative source of desktop state."""

    def __init__(self):
        self._context = DesktopContext()
        self._lock = threading.Lock()
        self._polling = False
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Win32 helpers
    # ------------------------------------------------------------------
    def _win32(self):
        import win32gui
        import win32process
        return win32gui, win32process

    def _process_name_for_pid(self, pid: int) -> str:
        try:
            import psutil
            proc = psutil.Process(pid)
            return proc.name()
        except Exception:
            return ""

    def _list_visible_windows(self) -> List[WindowInfo]:
        try:
            import win32gui
            import win32process
        except Exception:
            return []

        result: List[WindowInfo] = []

        def _enum(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                title = win32gui.GetWindowText(hwnd)
                if not title:
                    return True
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                result.append(
                    WindowInfo(
                        hwnd=hwnd,
                        title=title,
                        process_name=self._process_name_for_pid(pid),
                        pid=pid,
                    )
                )
            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(_enum, None)
        except Exception as e:
            logger.warning(f"EnumWindows failed: {e}")
        return result

    def _current_cursor(self):
        try:
            import win32api
            return win32api.GetCursorPos()
        except Exception:
            return (0, 0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> DesktopContext:
        """Refresh desktop context synchronously."""
        try:
            import win32gui
            import win32process
        except Exception:
            return self._context

        fg_hwnd = 0
        fg_title = ""
        fg_process = ""
        try:
            fg_hwnd = win32gui.GetForegroundWindow()
            fg_title = win32gui.GetWindowText(fg_hwnd)
            _, fg_pid = win32process.GetWindowThreadProcessId(fg_hwnd)
            fg_process = self._process_name_for_pid(fg_pid)
        except Exception:
            pass

        cx, cy = self._current_cursor()

        with self._lock:
            self._context = DesktopContext(
                foreground_hwnd=fg_hwnd,
                foreground_title=fg_title,
                foreground_process=fg_process,
                cursor_x=cx,
                cursor_y=cy,
                windows=self._list_visible_windows(),
                refreshed_at=time.monotonic(),
            )
        return self._context

    def get_context(self) -> DesktopContext:
        with self._lock:
            return self._context

    def find_window(self, target: str, process_hint: Optional[str] = None) -> Optional[WindowInfo]:
        """
        Find the best visible window matching a target string.
        Matches on window title (case-insensitive) and optionally process name.
        """
        target_l = target.lower()
        candidates = []
        ctx = self.get_context()
        for w in ctx.windows:
            title_l = w.title.lower()
            proc_l = w.process_name.lower()
            if process_hint and process_hint.lower() in proc_l and target_l in title_l:
                candidates.append(w)
            elif target_l in title_l:
                candidates.append(w)
        if not candidates:
            return None
        # prefer shorter titles (more specific) and process hint
        candidates.sort(key=lambda w: len(w.title))
        return candidates[0]

    def set_foreground(self, hwnd: int) -> bool:
        """Bring a window to the foreground (uses real Win32 calls)."""
        try:
            import win32gui
            import win32con
            import win32api
            import win32process
            import ctypes

            user32 = ctypes.windll.user32
            # Remove foreground restriction
            user32.ShowWindow(hwnd, win32con.SW_RESTORE)
            user32.BringWindowToTop(hwnd)

            fg_thread, _ = win32process.GetWindowThreadProcessId(
                win32gui.GetForegroundWindow()
            )
            target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)
            current_thread = win32api.GetCurrentThreadId()
            if fg_thread != current_thread:
                win32process.AttachThreadInput(current_thread, fg_thread, True)
            if target_thread != current_thread:
                win32process.AttachThreadInput(current_thread, target_thread, True)
            try:
                user32.SetForegroundWindow(hwnd)
            finally:
                if fg_thread != current_thread:
                    win32process.AttachThreadInput(current_thread, fg_thread, False)
                if target_thread != current_thread:
                    win32process.AttachThreadInput(current_thread, target_thread, False)
            return True
        except Exception as e:
            logger.warning(f"set_foreground failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------
    def start_polling(self, interval: float = 0.5):
        if self._polling:
            return
        self._polling = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="DesktopContext",
            args=(interval,),
        )
        self._thread.start()

    def stop_polling(self):
        self._polling = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _poll_loop(self, interval: float):
        while self._polling:
            try:
                self.refresh()
            except Exception as e:
                logger.debug(f"Desktop context poll error: {e}")
            time.sleep(interval)
