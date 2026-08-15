"""
AirOS Engine — Action Skills
A registry of EXPLICITLY registered desktop skills. Every skill has:
  - name
  - description
  - risk classification
  - parameter validation
  - a real Windows executor
  - a real Windows verifier

No raw shell, no arbitrary executable paths, no voice-to-shell path.
The ActionExecutor only invokes skills registered here.

Skills execute real Windows state changes and verify them:
  open_settings / open_app / switch_app / close_window / close_browser_tab /
  screenshot / volume / media / browser_navigation / minimize_window /
  maximize_window / scroll / type_text / system_settings_open
"""

import os
import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Any

logger = logging.getLogger(__name__)

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"
RISK_CRITICAL = "CRITICAL"

BROWSER_PROCESSES = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
    "opera.exe", "vivaldi.exe", "iexplore.exe",
}

# ---------------------------------------------------------------------------
# Application path resolver (no arbitrary paths — known apps only)
# ---------------------------------------------------------------------------

# aliases -> (kind, key)
# kind: "uri" -> os.startfile(uri); "app" -> resolve executable
APP_ALIASES: Dict[str, tuple] = {
    "settings": ("uri", "ms-settings:"),
    "windows settings": ("uri", "ms-settings:"),
    "control panel": ("app", "control.exe"),
    "chrome": ("app", "chrome.exe"),
    "google chrome": ("app", "chrome.exe"),
    "browser": ("app", "chrome.exe"),
    "edge": ("app", "msedge.exe"),
    "firefox": ("app", "firefox.exe"),
    "vscode": ("app", "code.exe"),
    "visual studio code": ("app", "code.exe"),
    "code": ("app", "code.exe"),
    "notepad": ("app", "notepad.exe"),
    "calculator": ("app", "calculator.exe"),
    "paint": ("app", "mspaint.exe"),
    "explorer": ("app", "explorer.exe"),
    "file explorer": ("app", "explorer.exe"),
    "files": ("app", "explorer.exe"),
    "terminal": ("app", "WindowsTerminal.exe"),
    "windows terminal": ("app", "WindowsTerminal.exe"),
    "cmd": ("app", "cmd.exe"),
    "command prompt": ("app", "cmd.exe"),
    "word": ("app", "winword.exe"),
    "excel": ("app", "excel.exe"),
    "powerpoint": ("app", "powerpnt.exe"),
    "task manager": ("app", "taskmgr.exe"),
    "spotify": ("app", "spotify.exe"),
    "discord": ("app", "Discord.exe"),
    "telegram": ("app", "Telegram.exe"),
    "slack": ("app", "slack.exe"),
    "snipping tool": ("app", "SnippingTool.exe"),
    "clock": ("app", "Clock.exe"),
    "camera": ("app", "WindowsCamera.exe"),
}

_KNOWN_APP_FALLBACKS = {
    "WindowsTerminal.exe": [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"),
    ],
}

_reg_paths = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
]


def _resolve_from_registry(exe_name: str) -> Optional[str]:
    import winreg
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for sub in _reg_paths:
            key_path = os.path.join(sub, exe_name)
            try:
                with winreg.OpenKey(root, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, None)
                    if value and os.path.exists(value):
                        return value
            except OSError:
                continue
    return None


def _resolve_from_known_dirs(exe_name: str) -> Optional[str]:
    candidates = [
        os.environ.get("ProgramFiles", "C:\\Program Files"),
        os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    search_dirs = [
        os.path.join(c, r"Google\Chrome\Application"),
        os.path.join(c, r"Microsoft\Edge\Application"),
        os.path.join(c, r"Mozilla Firefox"),
        os.path.join(c, r"Microsoft VS Code\bin"),
        os.path.join(c, r"BraveSoftware\Brave-Browser\Application"),
        os.path.join(c, r"Opera"),
    ]
    for base in candidates:
        for d in search_dirs:
            cand = os.path.join(base, d, exe_name)
            if os.path.exists(cand):
                return cand
    for cand in _KNOWN_APP_FALLBACKS.get(exe_name, []):
        if os.path.exists(cand):
            return cand
    return None


def resolve_app_executable(app: str) -> Optional[str]:
    """Resolve a known app alias to an executable path."""
    app_l = app.strip().lower()
    entry = APP_ALIASES.get(app_l)
    if entry is None:
        return None
    kind, key = entry
    if kind == "uri":
        return key  # caller distinguishes by prefix "ms-settings:" etc.
    exe_name = key
    path = _resolve_from_registry(exe_name)
    if path:
        return path
    path = _resolve_from_known_dirs(exe_name)
    if path:
        return path
    # system32 for built-ins
    sys32 = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", exe_name)
    if os.path.exists(sys32):
        return sys32
    return None


# ---------------------------------------------------------------------------
# Volume controller (Core Audio via pycaw — real, verifiable)
# ---------------------------------------------------------------------------

class VolumeController:
    """Real master volume control + readback via Windows Core Audio."""

    def __init__(self):
        self._endpoint = None
        self._lock = threading.Lock()
        self._init_volume()

    def _init_volume(self):
        try:
            from pycaw.pycaw import AudioUtilities
            device = AudioUtilities.GetSpeakers()
            self._endpoint = device.EndpointVolume
        except Exception as e:
            logger.warning(f"Volume controller unavailable: {e}")
            self._endpoint = None

    def get_state(self) -> Optional[dict]:
        if self._endpoint is None:
            return None
        try:
            return {
                "volume": round(self._endpoint.GetMasterVolumeLevelScalar() * 100.0, 1),
                "muted": bool(self._endpoint.GetMute()),
            }
        except Exception:
            return None

    def set_volume(self, percent: float) -> bool:
        if self._endpoint is None:
            return False
        try:
            value = max(0.0, min(1.0, percent / 100.0))
            self._endpoint.SetMasterVolumeLevelScalar(value, None)
            return True
        except Exception as e:
            logger.warning(f"Set volume failed: {e}")
            return False

    def change_volume(self, delta: float) -> bool:
        st = self.get_state()
        if st is None:
            return False
        return self.set_volume(st["volume"] + delta)

    def set_mute(self, muted: bool) -> bool:
        if self._endpoint is None:
            return False
        try:
            self._endpoint.SetMute(1 if muted else 0, None)
            return True
        except Exception:
            return False

    def toggle_mute(self) -> bool:
        st = self.get_state()
        if st is None:
            return False
        return self.set_mute(not st["muted"])


# ---------------------------------------------------------------------------
# Skill result
# ---------------------------------------------------------------------------

@dataclass
class SkillResult:
    ok: bool = False
    skill: str = ""
    message: str = ""
    verified: bool = False
    ambiguous: bool = False
    matches: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)
    requires_confirmation: bool = False


# ---------------------------------------------------------------------------
# Skill definitions
# ---------------------------------------------------------------------------

class Skill:
    """Base skill with executor + verifier hooks."""

    name: str = ""
    description: str = ""
    risk: str = RISK_LOW

    def validate_params(self, params: dict) -> Optional[str]:
        """Return error string if params are invalid, else None."""
        return None

    def execute(self, params: dict, deps: dict) -> SkillResult:
        raise NotImplementedError

    def verify(self, result: SkillResult, params: dict, deps: dict) -> bool:
        return False


class OpenAppSkill(Skill):
    name = "open_app"
    description = "Launch a known application (settings, chrome, vscode, notepad, ...)"
    risk = RISK_LOW

    def validate_params(self, params: dict) -> Optional[str]:
        app = (params.get("app") or params.get("target") or "").strip()
        if not app:
            return "missing app"
        if not resolve_app_executable(app):
            return f"unknown application: {app}"
        return None

    def execute(self, params: dict, deps: dict) -> SkillResult:
        app = (params.get("app") or params.get("target") or "").strip()
        resolved = resolve_app_executable(app)
        res = SkillResult(ok=False, skill=self.name, message=f"Could not resolve '{app}'")
        if resolved is None:
            return res
        try:
            if resolved.startswith("ms-settings:"):
                os.startfile(resolved)
            else:
                if resolved.lower().endswith((".exe", ".bat", ".cmd")):
                    os.startfile(resolved)
                else:
                    os.startfile(resolved)
            res.ok = True
            res.message = f"Launching {app}"
            res.detail = {"resolved": resolved}
        except Exception as e:
            res.message = f"Launch failed: {e}"
        return res

    def verify(self, result: SkillResult, params: dict, deps: dict) -> bool:
        ctx = deps.get("context")
        if not ctx:
            return False
        app = (params.get("app") or params.get("target") or "").strip().lower()
        if app in ("settings", "windows settings"):
            target_procs = ("applicationframehost.exe", "systemsettings.exe")
        else:
            target_procs = (app + ".exe",)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            ctx.refresh()
            for w in ctx.get_context().windows:
                if w.process_name.lower() in target_procs:
                    return True
                if app in w.title.lower() and w.process_name.lower() != "airosengine.exe":
                    return True
            time.sleep(0.3)
        return False


class SwitchAppSkill(Skill):
    name = "switch_app"
    description = "Bring a running application window to the foreground"
    risk = RISK_LOW

    def validate_params(self, params: dict) -> Optional[str]:
        target = (params.get("app") or params.get("target") or "").strip()
        if not target:
            return "missing target"
        return None

    def execute(self, params: dict, deps: dict) -> SkillResult:
        target = (params.get("app") or params.get("target") or "").strip()
        ctx = deps["context"]
        ctx.refresh()
        matches = []
        for w in ctx.get_context().windows:
            t_l = target.lower()
            if t_l in w.title.lower() or t_l in w.process_name.lower():
                matches.append(w)
        if not matches:
            return SkillResult(ok=False, skill=self.name, message=f"No window found for '{target}'")
        if len(matches) > 1:
            return SkillResult(
                ok=False, skill=self.name, ambiguous=True,
                matches=[m.to_dict() for m in matches[:10]],
                message=f"Multiple windows match '{target}'",
            )
        win = matches[0]
        ok = ctx.set_foreground(win.hwnd)
        return SkillResult(
            ok=ok, skill=self.name,
            message=f"Switched to {win.title}",
            detail={"hwnd": win.hwnd},
        )

    def verify(self, result: SkillResult, params: dict, deps: dict) -> bool:
        if not result.ok or result.ambiguous:
            return False
        ctx = deps["context"]
        time.sleep(0.4)
        ctx.refresh()
        fg = ctx.get_context().foreground_hwnd
        return fg == result.detail.get("hwnd")


class CloseWindowSkill(Skill):
    name = "close_window"
    description = "Close the foreground (or targeted) window"
    risk = RISK_MEDIUM

    def validate_params(self, params: dict) -> Optional[str]:
        return None

    def execute(self, params: dict, deps: dict) -> SkillResult:
        ctx = deps["context"]
        ctx.refresh()
        hwnd = params.get("hwnd") or ctx.get_context().foreground_hwnd
        title = params.get("target")
        if title:
            match = ctx.find_window(title)
            if match is None:
                return SkillResult(ok=False, skill=self.name, message=f"No window found matching '{title}'")
            hwnd = match.hwnd
        if not hwnd:
            return SkillResult(ok=False, skill=self.name, message="No window to close")
        try:
            import win32gui
            import win32con
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            return SkillResult(
                ok=True, skill=self.name,
                message="Close requested",
                detail={"hwnd": hwnd},
            )
        except Exception as e:
            return SkillResult(ok=False, skill=self.name, message=f"Close failed: {e}")

    def verify(self, result: SkillResult, params: dict, deps: dict) -> bool:
        if not result.ok:
            return False
        hwnd = result.detail.get("hwnd")
        ctx = deps["context"]
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            ctx.refresh()
            for w in ctx.get_context().windows:
                if w.hwnd == hwnd:
                    time.sleep(0.3)
                    break
            else:
                return True  # window gone
        return False


class CloseBrowserTabSkill(Skill):
    name = "close_browser_tab"
    description = "Close a specific browser tab (e.g. the Claude tab) or the active tab"
    risk = RISK_MEDIUM

    def validate_params(self, params: dict) -> Optional[str]:
        return None

    def execute(self, params: dict, deps: dict) -> SkillResult:
        ctx = deps["context"]
        inp = deps["input"]
        target = (params.get("target") or "").strip()
        ctx.refresh()
        windows = ctx.get_context().windows

        if target:
            matches = [
                w for w in windows
                if target.lower() in w.title.lower()
                and w.process_name.lower() in BROWSER_PROCESSES
            ]
            if not matches:
                return SkillResult(
                    ok=False, skill=self.name,
                    message=f"No browser tab found for '{target}'",
                )
            if len(matches) > 1:
                return SkillResult(
                    ok=False, skill=self.name, ambiguous=True,
                    matches=[m.to_dict() for m in matches[:10]],
                    message=f"Multiple tabs match '{target}'. Which one should I close?",
                )
            win = matches[0]
            ctx.set_foreground(win.hwnd)
            time.sleep(0.4)
            inp.hotkey(inp.VK.CONTROL, inp.VK.char_to_vk("w"))
            time.sleep(0.5)
            ctx.refresh()
            still = [
                w for w in ctx.get_context().windows
                if w.process_name.lower() in BROWSER_PROCESSES
                and target.lower() in w.title.lower()
            ]
            return SkillResult(
                ok=True, skill=self.name,
                message=f"Closed the {target} tab",
                detail={"target": target, "verified": len(still) == 0},
            )

        # no target -> close the active tab in the foreground browser
        fg_proc = ctx.get_context().foreground_process.lower()
        if fg_proc not in BROWSER_PROCESSES:
            return SkillResult(
                ok=False, skill=self.name,
                message="No browser is focused",
            )
        before_title = ctx.get_context().foreground_title
        inp.hotkey(inp.VK.CONTROL, inp.VK.char_to_vk("w"))
        time.sleep(0.5)
        ctx.refresh()
        after_title = ctx.get_context().foreground_title
        return SkillResult(
            ok=True, skill=self.name,
            message="Closed the active tab",
            detail={"title_changed": before_title != after_title},
        )

    def verify(self, result: SkillResult, params: dict, deps: dict) -> bool:
        if not result.ok or result.ambiguous:
            return False
        return bool(result.detail.get("verified", False))


class ScreenshotSkill(Skill):
    name = "screenshot"
    description = "Capture the screen (active monitor, primary, or all monitors)"
    risk = RISK_LOW

    def validate_params(self, params: dict) -> Optional[str]:
        target = (params.get("target") or "active").strip()
        if target not in ("active", "primary", "all"):
            return f"invalid target: {target}"
        return None

    def execute(self, params: dict, deps: dict) -> SkillResult:
        target = (params.get("target") or "active").strip()
        svc = deps["screenshot"]
        result = svc.capture(target=target)
        return SkillResult(
            ok=result.ok, skill=self.name,
            message=("Screenshot saved" if result.ok else f"Screenshot failed: {result.reason}"),
            detail={"path": result.path, "size": result.size_bytes},
        )

    def verify(self, result: SkillResult, params: dict, deps: dict) -> bool:
        return result.ok and bool(result.detail.get("path"))


class VolumeSkill(Skill):
    name = "volume"
    description = "Change, set, mute or unmute the system volume"
    risk = RISK_LOW

    def validate_params(self, params: dict) -> Optional[str]:
        action = (params.get("action") or params.get("target") or "").strip()
        if action not in ("up", "down", "mute", "unmute", "set"):
            return f"invalid volume action: {action}"
        if action == "set":
            try:
                float(params.get("value", 0))
            except (TypeError, ValueError):
                return "missing numeric value"
        return None

    def execute(self, params: dict, deps: dict) -> SkillResult:
        action = (params.get("action") or params.get("target") or "").strip()
        ctrl = deps["volume"]
        if ctrl.get_state() is None:
            return SkillResult(ok=False, skill=self.name, message="Volume control unavailable")
        if action == "up":
            ok = ctrl.change_volume(10.0)
        elif action == "down":
            ok = ctrl.change_volume(-10.0)
        elif action == "mute":
            ok = ctrl.set_mute(True)
        elif action == "unmute":
            ok = ctrl.set_mute(False)
        else:
            ok = ctrl.set_volume(float(params.get("value", 50)))
        return SkillResult(
            ok=ok, skill=self.name,
            message=f"Volume {action}",
            detail=ctrl.get_state() or {},
        )

    def verify(self, result: SkillResult, params: dict, deps: dict) -> bool:
        return result.ok and deps["volume"].get_state() is not None


class MediaSkill(Skill):
    name = "media"
    description = "Control media playback (play/pause, next, previous, stop)"
    risk = RISK_LOW

    def validate_params(self, params: dict) -> Optional[str]:
        action = (params.get("action") or params.get("target") or "").strip()
        if action not in ("play_pause", "next", "previous", "stop"):
            return f"invalid media action: {action}"
        return None

    def execute(self, params: dict, deps: dict) -> SkillResult:
        action = (params.get("action") or params.get("target") or "").strip()
        inp = deps["input"]
        vk = {
            "play_pause": inp.VK.MEDIA_PLAY_PAUSE,
            "next": inp.VK.MEDIA_NEXT_TRACK,
            "previous": inp.VK.MEDIA_PREV_TRACK,
            "stop": inp.VK.MEDIA_STOP,
        }[action]
        ok = inp.key_press(vk)
        return SkillResult(ok=ok, skill=self.name, message=f"Media {action}")

    def verify(self, result: SkillResult, params: dict, deps: dict) -> bool:
        # Media key injection cannot be reliably verified; report injected.
        return False


class BrowserNavigationSkill(Skill):
    name = "browser_navigation"
    description = "New tab, reopen tab, refresh, next tab, back, forward"
    risk = RISK_LOW

    _KEYS = {
        "new_tab": lambda inp: inp.hotkey(inp.VK.CONTROL, inp.VK.char_to_vk("t")),
        "reopen_tab": lambda inp: inp.hotkey(inp.VK.CONTROL, inp.VK.SHIFT, inp.VK.char_to_vk("t")),
        "refresh": lambda inp: inp.hotkey(inp.VK.CONTROL, inp.VK.char_to_vk("r")),
        "next_tab": lambda inp: inp.hotkey(inp.VK.CONTROL, inp.VK.TAB),
        "back": lambda inp: inp.hotkey(inp.VK.ALT, inp.VK.LEFT),
        "forward": lambda inp: inp.hotkey(inp.VK.ALT, inp.VK.RIGHT),
    }

    def validate_params(self, params: dict) -> Optional[str]:
        action = (params.get("action") or params.get("target") or "").strip()
        if action not in self._KEYS:
            return f"invalid browser action: {action}"
        return None

    def execute(self, params: dict, deps: dict) -> SkillResult:
        action = (params.get("action") or params.get("target") or "").strip()
        inp = deps["input"]
        ok = self._KEYS[action](inp)
        return SkillResult(ok=ok, skill=self.name, message=f"Browser {action}")

    def verify(self, result: SkillResult, params: dict, deps: dict) -> bool:
        return False


class MinimizeWindowSkill(Skill):
    name = "minimize_window"
    description = "Minimize the foreground window"
    risk = RISK_LOW

    def execute(self, params: dict, deps: dict) -> SkillResult:
        ctx = deps["context"]
        hwnd = ctx.get_context().foreground_hwnd
        try:
            import win32gui
            import win32con
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            return SkillResult(ok=True, skill=self.name, message="Window minimized", detail={"hwnd": hwnd})
        except Exception as e:
            return SkillResult(ok=False, skill=self.name, message=f"Minimize failed: {e}")

    def verify(self, result: SkillResult, params: dict, deps: dict) -> bool:
        return False


class MaximizeWindowSkill(Skill):
    name = "maximize_window"
    description = "Maximize (or restore) the foreground window"
    risk = RISK_LOW

    def execute(self, params: dict, deps: dict) -> SkillResult:
        ctx = deps["context"]
        hwnd = ctx.get_context().foreground_hwnd
        try:
            import win32gui
            import win32con
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            return SkillResult(ok=True, skill=self.name, message="Window maximized", detail={"hwnd": hwnd})
        except Exception as e:
            return SkillResult(ok=False, skill=self.name, message=f"Maximize failed: {e}")

    def verify(self, result: SkillResult, params: dict, deps: dict) -> bool:
        return False


class ScrollSkill(Skill):
    name = "scroll"
    description = "Scroll the active window up or down"
    risk = RISK_LOW

    def validate_params(self, params: dict) -> Optional[str]:
        direction = (params.get("direction") or params.get("action") or "").strip()
        if direction not in ("up", "down"):
            return f"invalid scroll direction: {direction}"
        return None

    def execute(self, params: dict, deps: dict) -> SkillResult:
        direction = (params.get("direction") or params.get("action") or "").strip()
        inp = deps["input"]
        lines = int(params.get("lines", 3))
        ok = inp.scroll_up(lines) if direction == "up" else inp.scroll_down(lines)
        return SkillResult(ok=ok, skill=self.name, message=f"Scroll {direction}")

    def verify(self, result: SkillResult, params: dict, deps: dict) -> bool:
        return False


class TypeTextSkill(Skill):
    name = "type_text"
    description = "Type text into the focused field"
    risk = RISK_MEDIUM

    def validate_params(self, params: dict) -> Optional[str]:
        text = params.get("text", "")
        if not isinstance(text, str) or not text.strip():
            return "missing text"
        return None

    def execute(self, params: dict, deps: dict) -> SkillResult:
        text = params.get("text", "")
        inp = deps["input"]
        ok = True
        for ch in text:
            if ch == "\n":
                ok = inp.key_press(inp.VK.RETURN) and ok
            elif ch == "\t":
                ok = inp.key_press(inp.VK.TAB) and ok
            else:
                ok = inp.type_unicode(ch) and ok
        return SkillResult(ok=ok, skill=self.name, message=f"Typed {len(text)} characters")

    def verify(self, result: SkillResult, params: dict, deps: dict) -> bool:
        return False


class SystemSettingsSkill(Skill):
    name = "system_settings_open"
    description = "Open a specific Windows Settings page (display, network, ...)"
    risk = RISK_LOW

    _PAGES = {
        "display": "display",
        "network": "network",
        "apps": "appsfeatures",
        "sound": "sound",
        "personalization": "personalization",
        "privacy": "privacy",
        "update": "windowsupdate",
        "bluetooth": "bluetooth",
        "about": "system",
        "default": "",
    }

    def validate_params(self, params: dict) -> Optional[str]:
        page = (params.get("page") or params.get("target") or "default").strip()
        if page not in self._PAGES:
            return f"unknown settings page: {page}"
        return None

    def execute(self, params: dict, deps: dict) -> SkillResult:
        page = (params.get("page") or params.get("target") or "default").strip()
        uri = f"ms-settings:{self._PAGES[page]}"
        try:
            os.startfile(uri)
            return SkillResult(ok=True, skill=self.name, message=f"Opened {page} settings", detail={"uri": uri})
        except Exception as e:
            return SkillResult(ok=False, skill=self.name, message=f"Open settings failed: {e}")

    def verify(self, result: SkillResult, params: dict, deps: dict) -> bool:
        ctx = deps["context"]
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            ctx.refresh()
            for w in ctx.get_context().windows:
                if w.process_name.lower() in ("applicationframehost.exe", "systemsettings.exe"):
                    return True
            time.sleep(0.3)
        return False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class SkillRegistry:
    """Authoritative registry of all executable skills."""

    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        for cls in (
            OpenAppSkill, SwitchAppSkill, CloseWindowSkill, CloseBrowserTabSkill,
            ScreenshotSkill, VolumeSkill, MediaSkill, BrowserNavigationSkill,
            MinimizeWindowSkill, MaximizeWindowSkill, ScrollSkill, TypeTextSkill,
            SystemSettingsSkill,
        ):
            skill = cls()
            self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def has(self, name: str) -> bool:
        return name in self._skills

    def list_skills(self) -> list:
        return [
            {
                "name": s.name,
                "description": s.description,
                "risk": s.risk,
            }
            for s in self._skills.values()
        ]
