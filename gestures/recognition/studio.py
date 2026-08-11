"""
AirOS — Gesture Studio
Facade that combines the recorder, matcher, and template persistence into a
single service the engine and IPC layer can drive.

Workflow:
  studio = GestureStudio()
  studio.start_recording("Swipe Up")
  # ... engine feeds landmarks every frame ...
  studio.record_frame(landmarks)          # while recording
  template = studio.finish_recording()    # saved to disk + added to matcher

  # Live matching (engine loop):
  matched_id = studio.match(landmarks, timestamp)
"""

import os
import uuid
import logging
from typing import List, Optional

from gestures.recognition.recorder import GestureRecorder
from gestures.recognition.matcher import GestureMatcher
from gestures.recognition.template import (
    GestureTemplate, templates_to_json, templates_from_json,
)
from config.paths import get_gestures_dir

logger = logging.getLogger(__name__)

DEFAULT_STORE_DIR = get_gestures_dir()
DEFAULT_STORE_FILE = "gesture_templates.json"


class GestureStudio:
    """Record, persist, and match custom gestures."""

    def __init__(self, store_file: Optional[str] = None):
        if store_file is None:
            store_file = os.path.join(DEFAULT_STORE_DIR, DEFAULT_STORE_FILE)
        self._store_file = os.path.abspath(store_file)
        self._recorder = GestureRecorder()
        self._matcher = GestureMatcher()
        self._templates: dict = {}
        self.load()

    # ── Persistence ──────────────────────────────────────────────────
    def load(self):
        if not os.path.exists(self._store_file):
            return
        try:
            with open(self._store_file, "r", encoding="utf-8") as f:
                templates = templates_from_json(f.read())
            for t in templates:
                self._templates[t.id] = t
                self._matcher.add_template(t)
            logger.info(f"GestureStudio loaded {len(templates)} templates")
        except Exception as e:
            logger.warning(f"Failed to load gesture templates: {e}")

    def save(self):
        os.makedirs(os.path.dirname(self._store_file), exist_ok=True)
        with open(self._store_file, "w", encoding="utf-8") as f:
            f.write(templates_to_json(list(self._templates.values())))

    # ── Recording ────────────────────────────────────────────────────
    @property
    def is_recording(self) -> bool:
        return self._recorder.is_recording

    def start_recording(self):
        self._recorder.start()

    def record_frame(self, landmarks) -> bool:
        return self._recorder.add_frame(landmarks)

    def finish_recording(self, name: str) -> Optional[GestureTemplate]:
        template = self._recorder.finish(name)
        if template is None:
            return None
        self._templates[template.id] = template
        self._matcher.add_template(template)
        self.save()
        logger.info(f"Gesture recorded: {template.name} ({template.frame_count} frames)")
        return template

    def cancel_recording(self):
        self._recorder.cancel()

    # ── Template management ──────────────────────────────────────────
    def list_templates(self) -> List[dict]:
        return [t.to_dict() for t in self._templates.values()]

    def get_template(self, template_id: str) -> Optional[GestureTemplate]:
        return self._templates.get(template_id)

    def delete_template(self, template_id: str) -> bool:
        if template_id not in self._templates:
            return False
        del self._templates[template_id]
        self._matcher.remove_template(template_id)
        self.save()
        logger.info(f"Gesture deleted: {template_id}")
        return True

    def rename_template(self, template_id: str, new_name: str) -> bool:
        t = self._templates.get(template_id)
        if t is None or not new_name.strip():
            return False
        t.name = new_name.strip()
        self.save()
        return True

    def set_template_action(self, template_id: str, action: str) -> bool:
        """Assign a safe-vocabulary action name to a template."""
        t = self._templates.get(template_id)
        if t is None or not action.strip():
            return False
        t.action = action.strip()
        self.save()
        return True

    def clear(self):
        self._templates.clear()
        self._matcher.clear_templates()
        self.save()

    # ── Matching ─────────────────────────────────────────────────────
    def match(self, landmarks, timestamp: float) -> Optional[str]:
        return self._matcher.update(landmarks, timestamp)

    def add_template(self, template: GestureTemplate):
        self._templates[template.id] = template
        self._matcher.add_template(template)
        self.save()

    def create_template_from_frames(self, name: str, frames) -> GestureTemplate:
        """Programmatic template creation (used by tests and tools)."""
        template = GestureTemplate.from_frames(name=name, frames=frames)
        self.add_template(template)
        return template
