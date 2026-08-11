"""
AirOS — Tests for the gesture registry, app profiles, and foreground detection.
Synthetic only — no webcam, no real window process names needed.
"""

import os
import sys
import json

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestGestureRegistry:
    def test_loads_system_gestures(self):
        from gestures.registry.manager import GestureRegistry
        reg = GestureRegistry()
        reg.load()
        gestures = reg.get_all()
        assert len(gestures) >= 9
        ids = {g.id for g in gestures}
        assert "pinch_click" in ids
        assert "open_palm" in ids
        assert "two_hands" in ids

    def test_get_all_enabled(self):
        from gestures.registry.manager import GestureRegistry
        reg = GestureRegistry()
        reg.load()
        assert all(g.enabled for g in reg.get_all_enabled())

    def test_get_by_id(self):
        from gestures.registry.manager import GestureRegistry
        reg = GestureRegistry()
        reg.load()
        pinch = reg.get_by_id("pinch_click")
        assert pinch is not None
        assert pinch.thresholds["distance"] == 0.30

    def test_get_threshold_default(self):
        from gestures.registry.manager import GestureRegistry
        reg = GestureRegistry()
        reg.load()
        assert reg.get_threshold("pinch_click", "distance") == 0.30
        assert reg.get_threshold("pinch_click", "nope", default=7) == 7


class FakeForeground:
    """Stub foreground detector returning a configurable app name."""
    def __init__(self, app="explorer.exe"):
        self.app = app

    def get_foreground_process(self):
        return self.app

    def get_foreground_window_title(self):
        return ""


class TestProfileManager:
    def _manager(self, app="explorer.exe", profiles_file=None):
        from gestures.registry.manager import GestureRegistry, GestureProfile
        from gestures.profiles.profile_manager import ProfileManager
        reg = GestureRegistry()
        reg.load()
        reg.set_active_profile("default")  # isolate from previous test runs
        reg.add_profile(GestureProfile(
            id="browser", name="Browser", active=False,
            app_matchers=["chrome.exe", "msedge.exe"],
        ))
        mgr = ProfileManager(registry=reg, foreground_detector=FakeForeground(app))
        return mgr, reg

    def test_no_match_keeps_default(self):
        mgr, _ = self._manager(app="notepad.exe")
        mgr.update(now=1000.0)
        assert mgr.active_profile_id == "default"

    def test_matches_browser_profile(self):
        mgr, reg = self._manager(app="chrome.exe")
        mgr.update(now=1000.0)
        assert mgr.active_profile_id == "browser"

    def test_rate_limited(self):
        mgr, _ = self._manager(app="chrome.exe")
        # First update at 1000s switches; second at 1000.2s is rate-limited
        mgr.update(now=1000.0)
        assert mgr.active_profile_id == "browser"
        # Force app to change; should NOT switch before poll interval
        mgr._foreground.app = "notepad.exe"
        mgr.update(now=1000.2)
        assert mgr.active_profile_id == "browser"

    def test_profile_changed_callback(self):
        mgr, _ = self._manager(app="chrome.exe")
        calls = []
        mgr.on_profile_changed(lambda pid: calls.append(pid))
        mgr.update(now=1000.0)
        assert calls == ["browser"]

    def test_manual_set_profile(self):
        mgr, reg = self._manager(app="notepad.exe")
        assert mgr.set_profile("browser")
        assert mgr.active_profile_id == "browser"

    def test_manual_set_unknown_profile_fails(self):
        mgr, _ = self._manager()
        assert not mgr.set_profile("missing")


class TestProfilePersistence:
    def test_profiles_roundtrip(self, tmp_path):
        from gestures.registry.manager import GestureRegistry, GestureProfile
        # Redirect profile dir to tmp by monkeypatching module constant
        import gestures.registry.manager as mgr_module
        orig = mgr_module.PROFILES_DIR
        mgr_module.PROFILES_DIR = str(tmp_path)
        try:
            reg = GestureRegistry()
            reg.load()
            reg.add_profile(GestureProfile(
                id="games", name="Games", active=False,
                app_matchers=["steam.exe"], gesture_overrides={"pinch_click": {"action": "left_click"}},
            ))
            reg.set_active_profile("games")
            reg2 = GestureRegistry()
            reg2.load()
            p = reg2.get_profile("games")
            assert p is not None
            assert p.app_matchers == ["steam.exe"]
            assert reg2.active_profile.id == "games"
        finally:
            mgr_module.PROFILES_DIR = orig

    def test_app_matcher_substring(self):
        from gestures.registry.manager import GestureProfile
        p = GestureProfile(id="x", name="X", active=False, app_matchers=["Chrome"])
        assert p.matches_app("chrome.exe")
        assert p.matches_app("CHROME.EXE")
        assert not p.matches_app("firefox.exe")
        assert not p.matches_app("")

    def test_get_profile_for_app_most_specific(self):
        from gestures.registry.manager import GestureRegistry, GestureProfile
        reg = GestureRegistry()
        reg.load()
        reg.add_profile(GestureProfile(id="p1", name="P1", active=False, app_matchers=["app.exe"]))
        reg.add_profile(GestureProfile(id="p2", name="P2", active=False, app_matchers=["app.exe editor"]))
        profile = reg.get_profile_for_app("app.exe editor")
        assert profile.id == "p2"

    def test_default_profile_cannot_be_removed(self):
        from gestures.registry.manager import GestureRegistry
        reg = GestureRegistry()
        reg.load()
        assert not reg.remove_profile("default")
