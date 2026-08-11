"""
AirOS Engine — Windows SendInput Adapter
Low-level Windows input injection using the SendInput Win32 API via ctypes.

This is the FINAL input layer. It never blocks the real-time pipeline.
All input calls are synchronous but fast (<1ms per call).

Architecture:
- Absolute mouse positioning (mapped to [0, 65535])
- Relative scroll (MOUSEEVENTF_WHEEL)
- Virtual key press/release
- Safety: all calls return number of events injected; failures are logged

References:
- https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput
- https://docs.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-input
"""

import ctypes
import ctypes.wintypes
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# =============================================================================
# Win32 Constants
# =============================================================================

# Mouse event flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000  # Use for multi-monitor absolute mapping

# Keyboard event flags
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

# Input types
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

# Scroll delta (standard Windows scroll unit)
WHEEL_DELTA = 120

# =============================================================================
# Win32 Structures
# =============================================================================

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.wintypes.DWORD),
        ("wParamL", ctypes.wintypes.WORD),
        ("wParamH", ctypes.wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("_input", _INPUT_UNION),
    ]


# Pointer to INPUT struct
LPINPUT = ctypes.POINTER(INPUT)


# =============================================================================
# Windows Input Adapter
# =============================================================================

class WindowsInputAdapter:
    """
    Wraps Win32 SendInput for mouse and keyboard injection.
    
    Provides:
    - move_cursor(x, y): Absolute cursor positioning
    - left_click(): Single left click
    - right_click(): Single right click
    - double_click(): Double left click
    - mouse_down(button): Mouse button down
    - mouse_up(button): Mouse button up
    - scroll(delta): Vertical scroll
    - key_press(vk_code): Press and release a virtual key
    - key_down(vk_code): Key down only
    - key_up(vk_code): Key up only
    - hotkey(*vk_codes): Press multiple keys simultaneously
    
    Safety:
    - enabled flag: when False, no input is injected (PAUSED/OFF state)
    - All failures are logged, never raised
    - Latency is measured and reported
    """

    def __init__(self):
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._enabled = True
        self._virtual_left: int = 0
        self._virtual_top: int = 0
        self._virtual_width: int = 0
        self._virtual_height: int = 0
        self._last_inject_time: float = 0.0
        self._inject_count: int = 0
        self._inject_failures: int = 0
        self._refresh_screen_size()

    def _refresh_screen_size(self):
        """Get virtual screen dimensions and origins (handles multi-monitor)."""
        SM_XVIRTUALSCREEN = 76
        SM_YVIRTUALSCREEN = 77
        SM_CXVIRTUALSCREEN = 78
        SM_CYVIRTUALSCREEN = 79
        self._virtual_left = self._user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        self._virtual_top = self._user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        self._virtual_width = self._user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        self._virtual_height = self._user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        if self._virtual_width == 0 or self._virtual_height == 0:
            # Fallback to primary screen
            self._virtual_left = 0
            self._virtual_top = 0
            self._virtual_width = self._user32.GetSystemMetrics(0)   # SM_CXSCREEN
            self._virtual_height = self._user32.GetSystemMetrics(1)  # SM_CYSCREEN
        logger.info(
            f"Screen size: origin=({self._virtual_left},{self._virtual_top}), "
            f"dim={self._virtual_width}x{self._virtual_height}"
        )

    def enable(self):
        """Enable input injection."""
        self._enabled = True

    def disable(self):
        """Disable input injection (PAUSED or OFF state)."""
        self._enabled = False

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def _send_input(self, *inputs: INPUT) -> int:
        """
        Call Win32 SendInput with the given INPUT structures.
        Returns number of events successfully injected (0 = failure).
        """
        if not self._enabled:
            return 0

        n = len(inputs)
        input_array = (INPUT * n)(*inputs)
        t0 = time.monotonic()
        result = self._user32.SendInput(n, input_array, ctypes.sizeof(INPUT))
        self._last_inject_time = (time.monotonic() - t0) * 1000  # ms

        if result != n:
            err = ctypes.get_last_error()
            logger.warning(f"SendInput injected {result}/{n} events. Error: {err}")
            self._inject_failures += 1
        else:
            self._inject_count += result

        return result

    def _make_mouse_input(
        self,
        dx: int = 0,
        dy: int = 0,
        flags: int = 0,
        mouse_data: int = 0,
    ) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp._input.mi.dx = dx
        inp._input.mi.dy = dy
        inp._input.mi.mouseData = mouse_data
        inp._input.mi.dwFlags = flags
        inp._input.mi.time = 0
        inp._input.mi.dwExtraInfo = None
        return inp

    def _make_keyboard_input(
        self,
        vk_code: int,
        flags: int = 0,
    ) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp._input.ki.wVk = vk_code
        inp._input.ki.wScan = 0
        inp._input.ki.dwFlags = flags
        inp._input.ki.time = 0
        inp._input.ki.dwExtraInfo = None
        return inp

    def _screen_to_absolute(self, x: int, y: int) -> tuple[int, int]:
        """
        Convert screen pixel coordinates to absolute SendInput coordinates [0, 65535].
        Handles virtual (multi-monitor) screen space with negative origins.
        """
        if self._virtual_width > 1 and self._virtual_height > 1:
            abs_x = int(((x - self._virtual_left) * 65535) / (self._virtual_width - 1))
            abs_y = int(((y - self._virtual_top) * 65535) / (self._virtual_height - 1))
        else:
            abs_x = x
            abs_y = y
        return (
            max(0, min(65535, abs_x)),
            max(0, min(65535, abs_y)),
        )

    def move_cursor(self, screen_x: int, screen_y: int) -> bool:
        """
        Move cursor to absolute screen position (pixels).
        Returns True if injection succeeded.
        """
        abs_x, abs_y = self._screen_to_absolute(screen_x, screen_y)
        inp = self._make_mouse_input(
            dx=abs_x,
            dy=abs_y,
            flags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
        )
        return self._send_input(inp) > 0

    def mouse_down(self, button: str = "left") -> bool:
        """Press (but don't release) a mouse button."""
        flags = {
            "left": MOUSEEVENTF_LEFTDOWN,
            "right": MOUSEEVENTF_RIGHTDOWN,
            "middle": MOUSEEVENTF_MIDDLEDOWN,
        }.get(button, MOUSEEVENTF_LEFTDOWN)
        inp = self._make_mouse_input(flags=flags)
        return self._send_input(inp) > 0

    def mouse_up(self, button: str = "left") -> bool:
        """Release a mouse button."""
        flags = {
            "left": MOUSEEVENTF_LEFTUP,
            "right": MOUSEEVENTF_RIGHTUP,
            "middle": MOUSEEVENTF_MIDDLEUP,
        }.get(button, MOUSEEVENTF_LEFTUP)
        inp = self._make_mouse_input(flags=flags)
        return self._send_input(inp) > 0

    def left_click(self) -> bool:
        """Single left click (down + up as atomic pair)."""
        down = self._make_mouse_input(flags=MOUSEEVENTF_LEFTDOWN)
        up = self._make_mouse_input(flags=MOUSEEVENTF_LEFTUP)
        return self._send_input(down, up) == 2

    def right_click(self) -> bool:
        """Single right click."""
        down = self._make_mouse_input(flags=MOUSEEVENTF_RIGHTDOWN)
        up = self._make_mouse_input(flags=MOUSEEVENTF_RIGHTUP)
        return self._send_input(down, up) == 2

    def double_click(self) -> bool:
        """Double left click."""
        success = self.left_click()
        time.sleep(0.05)  # Small delay between clicks
        success = success and self.left_click()
        return success

    def scroll(self, delta: int) -> bool:
        """
        Vertical scroll.
        delta > 0: scroll up (positive WHEEL_DELTA)
        delta < 0: scroll down
        Typically use multiples of WHEEL_DELTA (120) for standard scroll speed.
        """
        inp = self._make_mouse_input(
            flags=MOUSEEVENTF_WHEEL,
            mouse_data=ctypes.c_ulong(delta).value,
        )
        return self._send_input(inp) > 0

    def scroll_up(self, lines: int = 3) -> bool:
        """Scroll up by N standard units."""
        return self.scroll(WHEEL_DELTA * lines)

    def scroll_down(self, lines: int = 3) -> bool:
        """Scroll down by N standard units."""
        return self.scroll(-WHEEL_DELTA * lines)

    def key_down(self, vk_code: int) -> bool:
        """Press a virtual key (without release)."""
        inp = self._make_keyboard_input(vk_code, flags=0)
        return self._send_input(inp) > 0

    def key_up(self, vk_code: int) -> bool:
        """Release a virtual key."""
        inp = self._make_keyboard_input(vk_code, flags=KEYEVENTF_KEYUP)
        return self._send_input(inp) > 0

    def key_press(self, vk_code: int) -> bool:
        """Press and release a virtual key."""
        down = self._make_keyboard_input(vk_code, flags=0)
        up = self._make_keyboard_input(vk_code, flags=KEYEVENTF_KEYUP)
        return self._send_input(down, up) == 2

    def type_unicode(self, char: str) -> bool:
        """
        Type a single character using its Unicode value.
        Handles case correctly (KEYEVENTF_UNICODE) without shift-state tracking.
        """
        if len(char) != 1:
            return False
        code = ord(char)
        down = self._make_keyboard_input(0, flags=KEYEVENTF_UNICODE)
        down._input.ki.wScan = code
        up = self._make_keyboard_input(0, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
        up._input.ki.wScan = code
        return self._send_input(down, up) == 2

    def hotkey(self, *vk_codes: int) -> bool:
        """
        Press a key combination (e.g., hotkey(VK_CONTROL, VK_ALT, VK_DELETE)).
        All keys pressed then released in reverse order.
        """
        down_inputs = [self._make_keyboard_input(vk, 0) for vk in vk_codes]
        up_inputs = [self._make_keyboard_input(vk, KEYEVENTF_KEYUP) for vk in reversed(vk_codes)]
        all_inputs = down_inputs + up_inputs
        return self._send_input(*all_inputs) == len(all_inputs)

    def get_metrics(self) -> dict:
        return {
            "inject_count": self._inject_count,
            "inject_failures": self._inject_failures,
            "last_inject_ms": round(self._last_inject_time, 3),
            "enabled": self._enabled,
        }


# =============================================================================
# Common Virtual Key Codes
# =============================================================================

class VK:
    """Common Windows Virtual Key codes."""
    # Mouse buttons
    LBUTTON = 0x01
    RBUTTON = 0x02

    # Standard keys
    BACK = 0x08        # Backspace
    TAB = 0x09
    RETURN = 0x0D      # Enter
    ESCAPE = 0x1B
    SPACE = 0x20
    END = 0x23
    HOME = 0x24
    LEFT = 0x25
    UP = 0x26
    RIGHT = 0x27
    DOWN = 0x28
    DELETE = 0x2E
    PAGE_UP = 0x21
    PAGE_DOWN = 0x22

    # Modifiers
    SHIFT = 0x10
    CONTROL = 0x11
    ALT = 0x12         # VK_MENU
    LWIN = 0x5B
    RWIN = 0x5C

    # Function keys
    F1 = 0x70
    F2 = 0x71
    F3 = 0x72
    F4 = 0x73
    F5 = 0x74

    # Media keys
    VOLUME_MUTE = 0xAD
    VOLUME_DOWN = 0xAE
    VOLUME_UP = 0xAF
    MEDIA_NEXT_TRACK = 0xB0
    MEDIA_PREV_TRACK = 0xB1
    MEDIA_STOP = 0xB2
    MEDIA_PLAY_PAUSE = 0xB3

    # Browser keys
    BROWSER_BACK = 0xA6
    BROWSER_FORWARD = 0xA7
    BROWSER_REFRESH = 0xA8

    # Letter keys (A=0x41 ... Z=0x5A)
    @staticmethod
    def char_to_vk(c: str) -> int:
        """Convert a letter A-Z or digit 0-9 to its VK code."""
        c = c.upper()
        if 'A' <= c <= 'Z':
            return ord(c)
        if '0' <= c <= '9':
            return ord(c)
        return 0
