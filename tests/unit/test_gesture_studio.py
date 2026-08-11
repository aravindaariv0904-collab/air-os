"""
AirOS — Tests for the Gesture Studio backend (recorder, matcher, templates).
These tests run without a webcam or MediaPipe model (synthetic landmarks only).
"""

import os
import sys
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# MediaPipe hand landmark indices (used to build synthetic landmarks)
WRIST = 0
INDEX_TIP = 8
MIDDLE_MCP = 9


def _synthetic_hand(index_x=0.5, index_y=0.5) -> np.ndarray:
    """Build a plausible (21, 3) landmark array. Only a few joints matter."""
    lm = np.zeros((21, 3), dtype=np.float32)
    lm[WRIST] = [index_x - 0.08, 0.5, 0.0]
    lm[MIDDLE_MCP] = [index_x - 0.02, 0.5, 0.0]
    lm[INDEX_TIP] = [index_x, index_y, 0.0]
    # Fill other landmarks with values that keep normalization sane.
    for i in range(1, 21):
        if np.all(lm[i] == 0):
            lm[i] = [index_x - 0.04 + i * 0.002, 0.5 + i * 0.003, 0.0]
    return lm


def _curl_features(n=30):
    """Normalized feature sequence for an index-finger curl (shape change).

    Wrist stays fixed; the index tip curls from high (extended) to low
    (tucked), which changes the hand shape rather than just translating it.
    """
    from gestures.recognition.features import landmark_frame_to_features
    frames = [_synthetic_hand(index_y=0.4 - i * (0.3 / (n - 1))) for i in range(n)]
    return np.stack([landmark_frame_to_features(f) for f in frames], axis=0).astype(np.float32)


class TestGestureRecorder:
    def test_record_finish_resamples_to_fixed_length(self):
        from gestures.recognition.recorder import GestureRecorder
        rec = GestureRecorder(target_frames=30)
        rec.start()
        assert rec.is_recording
        for i in range(10):
            rec.add_frame(_synthetic_hand(index_x=0.4 + i * 0.01))
        template = rec.finish("Wave")
        assert template is not None
        assert template.name == "Wave"
        assert template.frames.shape == (30, 42)

    def test_finish_without_recording_returns_none(self):
        from gestures.recognition.recorder import GestureRecorder
        rec = GestureRecorder()
        assert rec.finish("X") is None

    def test_finish_too_short_returns_none(self):
        from gestures.recognition.recorder import GestureRecorder
        rec = GestureRecorder()
        rec.start()
        rec.add_frame(_synthetic_hand())
        assert rec.finish("X") is None

    def test_cancel_stops_recording(self):
        from gestures.recognition.recorder import GestureRecorder
        rec = GestureRecorder()
        rec.start()
        rec.cancel()
        assert not rec.is_recording
        assert rec.frame_count == 0


class TestGestureMatcher:
    def test_no_templates_returns_none(self):
        from gestures.recognition.matcher import GestureMatcher
        matcher = GestureMatcher()
        assert matcher.update(_synthetic_hand(), time.monotonic()) is None

    def test_matches_similar_gesture(self):
        from gestures.recognition.matcher import GestureMatcher
        from gestures.recognition.template import GestureTemplate
        template = GestureTemplate.from_frames(name="Curl", frames=_curl_features(), gesture_id="curl")
        matcher = GestureMatcher(distance_threshold=0.15, confirm_frames=2)
        matcher.add_template(template)

        # Live: same curl, then hold the final pose so confirmation can fire
        t = time.monotonic()
        matched = None
        for i in range(33):
            y = 0.4 - min(i, 29) * (0.3 / 29)  # curl, then hold final
            matched = matcher.update(_synthetic_hand(index_y=y), t)
            if matched:
                break
            t += 1 / 30.0
        assert matched == "curl"

    def test_does_not_match_different_gesture(self):
        from gestures.recognition.matcher import GestureMatcher
        from gestures.recognition.template import GestureTemplate
        template = GestureTemplate.from_frames(name="Curl", frames=_curl_features(), gesture_id="curl")
        matcher = GestureMatcher(distance_threshold=0.15, confirm_frames=2)
        matcher.add_template(template)

        # Live: a different motion — index moves up, then back (opposite shape)
        t = time.monotonic()
        matched = None
        for i in range(33):
            y = 0.1 + min(i, 29) * (0.3 / 29)  # 0.1 -> 0.4, opposite of curl
            matched = matcher.update(_synthetic_hand(index_y=y), t)
            t += 1 / 30.0
        assert matched is None

    def test_remove_template(self):
        from gestures.recognition.matcher import GestureMatcher
        from gestures.recognition.template import GestureTemplate
        frames = np.zeros((5, 42), dtype=np.float32)
        template = GestureTemplate.from_frames(name="T", frames=frames, gesture_id="t1")
        matcher = GestureMatcher()
        matcher.add_template(template)
        assert matcher.template_ids == ["t1"]
        assert matcher.remove_template("t1")
        assert matcher.template_ids == []

    def test_cooldown_prevents_rapid_firing(self):
        from gestures.recognition.matcher import GestureMatcher
        from gestures.recognition.template import GestureTemplate
        template = GestureTemplate.from_frames(name="Curl", frames=_curl_features(), gesture_id="curl")
        matcher = GestureMatcher(distance_threshold=0.15, confirm_frames=2, cooldown=60.0)
        matcher.add_template(template)

        t = time.monotonic()
        fires = 0
        # Two back-to-back curls (with hold); cooldown should suppress the second
        for _ in range(2):
            for i in range(33):
                y = 0.4 - min(i, 29) * (0.3 / 29)
                if matcher.update(_synthetic_hand(index_y=y), t):
                    fires += 1
                t += 1 / 30.0
        assert fires == 1


class TestGestureStudio:
    def _make_studio(self, tmp_path):
        from gestures.recognition.studio import GestureStudio
        return GestureStudio(store_file=str(tmp_path / "templates.json"))

    def test_record_and_persist(self, tmp_path):
        studio = self._make_studio(tmp_path)
        studio.start_recording()
        for i in range(10):
            studio.record_frame(_synthetic_hand(index_x=0.4 + i * 0.01))
        template = studio.finish_recording("Upwave")
        assert template is not None
        assert studio.get_template(template.id) is not None

        # Reload from disk
        studio2 = self._make_studio(tmp_path)
        assert studio2.get_template(template.id) is not None

    def test_delete_template(self, tmp_path):
        studio = self._make_studio(tmp_path)
        studio.start_recording()
        for i in range(10):
            studio.record_frame(_synthetic_hand(index_x=0.4 + i * 0.01))
        template = studio.finish_recording("Todel")
        assert studio.delete_template(template.id)
        assert not studio.delete_template(template.id)

    def test_cancel_recording(self, tmp_path):
        studio = self._make_studio(tmp_path)
        studio.start_recording()
        studio.record_frame(_synthetic_hand())
        studio.cancel_recording()
        assert not studio.is_recording

    def test_rename_template(self, tmp_path):
        studio = self._make_studio(tmp_path)
        frames = np.zeros((5, 42), dtype=np.float32)
        template = studio.create_template_from_frames("Old", frames)
        assert studio.rename_template(template.id, "New")
        assert studio.get_template(template.id).name == "New"

    def test_rename_requires_valid_id(self, tmp_path):
        studio = self._make_studio(tmp_path)
        assert not studio.rename_template("missing", "X")

    def test_set_template_action(self, tmp_path):
        studio = self._make_studio(tmp_path)
        frames = _curl_features()
        template = studio.create_template_from_frames("G", frames)
        assert studio.set_template_action(template.id, "volume_up")
        assert studio.get_template(template.id).action == "volume_up"
        assert not studio.set_template_action(template.id, "")
        assert not studio.set_template_action("missing", "volume_up")

    def test_list_templates(self, tmp_path):
        studio = self._make_studio(tmp_path)
        studio.create_template_from_frames("A", _curl_features())
        studio.create_template_from_frames("B", _curl_features())
        assert len(studio.list_templates()) == 2

    def test_match_through_studio(self, tmp_path):
        from gestures.recognition.template import GestureTemplate
        studio = self._make_studio(tmp_path)
        template = GestureTemplate.from_frames(name="Curl", frames=_curl_features(), gesture_id="curl")
        studio.add_template(template)

        t = time.monotonic()
        matched = None
        for i in range(33):
            y = 0.4 - min(i, 29) * (0.3 / 29)
            matched = studio.match(_synthetic_hand(index_y=y), t)
            if matched:
                break
            t += 1 / 30.0
        assert matched == "curl"
