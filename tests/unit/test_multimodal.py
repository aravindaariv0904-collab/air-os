"""
Unit tests for AirOS multimodal subsystems:
  - BlinkDetector (single + triple blink from simulated EAR)
  - Intent parser (voice command routing)
  - Skill parameter validation
  - ActionExecutor (mock deps, no real Windows side effects)
  - VoiceAssistant text-command pipeline (mock executor)
"""

import time

import pytest


# =============================================================================
# BlinkDetector
# =============================================================================

class TestBlinkDetector:
    def _make(self, **kw):
        from engine.vision.blink_detector import BlinkDetector
        return BlinkDetector(**kw)

    def test_single_blink(self):
        det = self._make()
        t0 = time.monotonic()  # base time avoids the initial-cooldown window
        det.update(0.30, True, timestamp=t0)          # OPEN
        det.update(0.08, True, timestamp=t0 + 0.2)    # CLOSED (200ms)
        det.update(0.30, True, timestamp=t0 + 0.35)   # OPEN (closed 150ms)
        ev = det.consume_event()
        assert ev == "blink"
        assert det.get_state().blink_count == 1

    def test_triple_blink_fires_event(self):
        det = self._make()
        t0 = time.monotonic()
        # blink 1
        det.update(0.30, True, timestamp=t0)
        det.update(0.08, True, timestamp=t0 + 0.2)
        det.update(0.30, True, timestamp=t0 + 0.35)
        det.consume_event()  # clear single blink
        # blink 2
        det.update(0.08, True, timestamp=t0 + 0.6)
        det.update(0.30, True, timestamp=t0 + 0.75)
        det.consume_event()
        # blink 3 -> triple
        det.update(0.08, True, timestamp=t0 + 1.0)
        det.update(0.30, True, timestamp=t0 + 1.15)
        ev = det.consume_event()
        assert ev == "triple_blink"
        assert det.get_state().triple_blink_count == 1

    def test_no_face_no_blink(self):
        det = self._make()
        t0 = time.monotonic()
        det.update(0.30, False, timestamp=t0)
        det.update(0.08, False, timestamp=t0 + 0.2)
        det.update(0.30, False, timestamp=t0 + 0.35)
        ev = det.consume_event()
        assert ev == "none"

    def test_to_dict_shape(self):
        det = self._make()
        d = det.to_dict()
        for key in ("eye_state", "ear", "face_present", "blink_count",
                    "blink_rate_bpm", "triple_blink_count", "last_event"):
            assert key in d


# =============================================================================
# Intent parser
# =============================================================================

class TestIntentParser:
    def _parse(self, text):
        from engine.voice.intent import parse_intent
        return parse_intent(text)

    def test_open_settings(self):
        i = self._parse("open settings")
        assert i.recognized and i.skill == "open_app"
        assert i.params["app"] == "settings"

    def test_screenshot(self):
        i = self._parse("take a screenshot")
        assert i.recognized and i.skill == "screenshot"

    def test_fullscreen_screenshot(self):
        i = self._parse("capture the full screen")
        assert i.skill == "screenshot" and i.params["target"] == "all"

    def test_volume_up(self):
        i = self._parse("increase the volume")
        assert i.recognized and i.skill == "volume" and i.params["action"] == "up"

    def test_volume_set(self):
        i = self._parse("set volume to fifty")
        assert i.skill == "volume" and i.params["action"] == "set"
        assert i.params["value"] == 50

    def test_volume_mute(self):
        i = self._parse("mute")
        assert i.skill == "volume" and i.params["action"] == "mute"

    def test_media_next(self):
        i = self._parse("next song")
        assert i.skill == "media" and i.params["action"] == "next"

    def test_close_tab(self):
        i = self._parse("close the claude tab")
        assert i.skill == "close_browser_tab" and i.params["target"] == "claude"

    def test_close_window(self):
        i = self._parse("close this window")
        assert i.skill == "close_window"

    def test_switch_app(self):
        i = self._parse("switch to vscode")
        assert i.skill == "switch_app" and i.params["app"] == "vscode"

    def test_minimize(self):
        i = self._parse("minimize")
        assert i.skill == "minimize_window"

    def test_scroll_down(self):
        i = self._parse("scroll down")
        assert i.skill == "scroll" and i.params["direction"] == "down"

    def test_settings_page(self):
        i = self._parse("open sound settings")
        assert i.skill == "system_settings_open" and i.params["page"] == "sound"

    def test_unknown(self):
        i = self._parse("gibberish words here")
        assert not i.recognized


# =============================================================================
# Skill parameter validation
# =============================================================================

class TestSkillValidation:
    def _registry(self):
        from engine.actions.skills import SkillRegistry
        return SkillRegistry()

    def test_open_app_unknown(self):
        r = self._registry()
        err = r.get("open_app").validate_params({"app": "definitely_not_an_app"})
        assert err is not None

    def test_volume_set_requires_number(self):
        r = self._registry()
        assert r.get("volume").validate_params({"action": "set", "value": 50}) is None
        assert r.get("volume").validate_params({"action": "set", "value": "fifty"}) is not None

    def test_screenshot_target(self):
        r = self._registry()
        assert r.get("screenshot").validate_params({"target": "all"}) is None
        assert r.get("screenshot").validate_params({"target": "bogus"}) is not None

    def test_browser_action(self):
        r = self._registry()
        assert r.get("browser_navigation").validate_params({"action": "refresh"}) is None
        assert r.get("browser_navigation").validate_params({"action": "bogus"}) is not None

    def test_scroll_direction(self):
        r = self._registry()
        assert r.get("scroll").validate_params({"direction": "up"}) is None
        assert r.get("scroll").validate_params({"direction": "sideways"}) is not None

    def test_type_text_requires_text(self):
        r = self._registry()
        assert r.get("type_text").validate_params({"text": "hello"}) is None
        assert r.get("type_text").validate_params({"text": " "}) is not None

    def test_settings_page(self):
        r = self._registry()
        assert r.get("system_settings_open").validate_params({"page": "display"}) is None
        assert r.get("system_settings_open").validate_params({"page": "bogus"}) is not None

    def test_unknown_skill_not_registered(self):
        r = self._registry()
        assert not r.has("no_such_skill")


# =============================================================================
# ActionExecutor with mock deps
# =============================================================================

class MockScreenshotService:
    def __init__(self):
        from input.screenshot import ScreenshotResult
        self.result = ScreenshotResult(ok=True, path=r"C:\tmp\shot.png", reason="ok", size_bytes=1024)

    def capture(self, target="active", path=None):
        return self.result


class MockVolumeController:
    def __init__(self):
        self.state = {"volume": 30.0, "muted": False}
        self.calls = []

    def get_state(self):
        return dict(self.state)

    def set_volume(self, percent):
        self.calls.append(("set", percent))
        self.state["volume"] = float(percent)
        return True

    def change_volume(self, delta):
        self.calls.append(("change", delta))
        self.state["volume"] = max(0.0, min(100.0, self.state["volume"] + delta))
        return True

    def set_mute(self, muted):
        self.calls.append(("mute", muted))
        self.state["muted"] = muted
        return True

    def toggle_mute(self):
        self.state["muted"] = not self.state["muted"]
        return True


class MockInput:
    VK = None
    def __init__(self):
        from input.windows.send_input import VK
        self.VK = VK
        self.pressed = []
    def key_press(self, vk):
        self.pressed.append(vk)
        return True
    def hotkey(self, *vks):
        self.pressed.extend(vks)
        return True
    def type_unicode(self, ch):
        return True


class TestActionExecutor:
    def _executor(self, verify=False, **extra_deps):
        from engine.actions.executor import ActionExecutor
        deps = {
            "context": None,
            "input": MockInput(),
            "screenshot": MockScreenshotService(),
            "volume": MockVolumeController(),
        }
        deps.update(extra_deps)
        ex = ActionExecutor(deps)
        return ex

    def test_unknown_skill(self):
        ex = self._executor()
        resp = ex.execute("no_such_skill", {})
        assert not resp.ok and "Unknown" in resp.message

    def test_screenshot_execute(self):
        ex = self._executor()
        resp = ex.execute("screenshot", {"target": "active"}, verify=False)
        assert resp.ok and resp.skill == "screenshot"

    def test_screenshot_verify_path(self):
        ex = self._executor(verify=False)
        resp = ex.execute("screenshot", {"target": "active"}, verify=False)
        assert resp.verified is False  # not verified when verify=False

    def test_volume_mute(self):
        ex = self._executor()
        resp = ex.execute("volume", {"action": "mute"}, verify=False)
        assert resp.ok
        assert ex._deps["volume"].state["muted"] is True

    def test_volume_invalid_params(self):
        ex = self._executor()
        resp = ex.execute("volume", {"action": "set", "value": "abc"}, verify=False)
        assert not resp.ok and "Invalid parameters" in resp.message

    def test_executor_never_raises(self):
        ex = self._executor()
        resp = ex.execute("screenshot", {"target": "all"}, verify=False)
        assert resp is not None


# =============================================================================
# VoiceAssistant text-command pipeline (mock executor + TTS)
# =============================================================================

class DummyExecutor:
    def __init__(self):
        self.executed = []

    def execute(self, skill, params):
        self.executed.append((skill, params))
        from engine.actions.executor import ActionResponse
        return ActionResponse(ok=True, skill=skill, message="ok", verified=False, ambiguous=False)


class DummyTTS:
    available = False
    def speak(self, text):
        return False


class TestVoiceAssistantPipeline:
    def _assistant(self):
        import engine.voice.assistant as va
        va.SpeechOutput = DummyTTS
        dummy = DummyExecutor()
        a = va.VoiceAssistant(executor=dummy, tts_enabled=False, on_event=None)
        return a, dummy

    def test_text_command_routes_to_executor(self):
        a, dummy = self._assistant()
        result = a.send_text_command("open settings")
        assert result is not None
        assert dummy.executed and dummy.executed[0][0] == "open_app"
        assert dummy.executed[0][1]["app"] == "settings"

    def test_unrecognized_does_not_execute(self):
        a, dummy = self._assistant()
        result = a.send_text_command("purple monkey dishwasher")
        assert result is None
        assert dummy.executed == []

    def test_status_shape(self):
        a, _ = self._assistant()
        s = a.get_status()
        for key in ("state", "enabled", "wake_word", "last_transcript",
                    "wake_count", "tts_available", "recognizer_initialized"):
            assert key in s
