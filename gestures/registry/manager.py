"""
AirOS — Gesture Registry Manager
Loads, validates, and provides gesture definitions from JSON.
Supports system gestures + custom gestures + per-app profiles.
"""

import json
import os
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

import shutil
from config.paths import get_profiles_dir

logger = logging.getLogger(__name__)

REGISTRY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
SYSTEM_GESTURES_FILE = os.path.join(REGISTRY_DIR, "system_gestures.json")

PROFILES_DIR = get_profiles_dir()
SEED_PROFILES_FILE = os.path.join(os.path.dirname(REGISTRY_DIR), "profiles", "profiles.json")
TARGET_PROFILES_FILE = os.path.join(PROFILES_DIR, "profiles.json")

if not os.path.exists(TARGET_PROFILES_FILE) and os.path.exists(SEED_PROFILES_FILE):
    try:
        shutil.copy2(SEED_PROFILES_FILE, TARGET_PROFILES_FILE)
    except Exception as e:
        logger.warning(f"Could not seed profiles.json to APPDATA: {e}")
CUSTOM_DIR = os.path.join(os.path.dirname(REGISTRY_DIR), "custom")


@dataclass
class GestureDefinition:
    """A single gesture definition."""
    id: str
    name: str
    emoji: str
    description: str
    type: str
    enabled: bool
    system: bool
    action: str
    scope: str
    thresholds: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "emoji": self.emoji,
            "description": self.description,
            "type": self.type,
            "enabled": self.enabled,
            "system": self.system,
            "action": self.action,
            "scope": self.scope,
            "thresholds": self.thresholds,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GestureDefinition":
        return cls(
            id=d["id"],
            name=d["name"],
            emoji=d.get("emoji", ""),
            description=d.get("description", ""),
            type=d["type"],
            enabled=d.get("enabled", True),
            system=d.get("system", False),
            action=d["action"],
            scope=d.get("scope", "global"),
            thresholds=d.get("thresholds", {}),
        )


@dataclass
class GestureProfile:
    """An app-specific or user-defined gesture profile."""
    id: str
    name: str
    active: bool
    app_matchers: List[str] = field(default_factory=list)
    gesture_overrides: Dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "active": self.active,
            "app_matchers": list(self.app_matchers),
            "gesture_overrides": self.gesture_overrides,
        }

    def matches_app(self, app_name: str) -> bool:
        """True if `app_name` (lowercase exe, e.g. 'chrome.exe') matches any
        app matcher. Matchers are case-insensitive substring matches."""
        if not app_name:
            return False
        app_name = app_name.lower()
        for matcher in self.app_matchers:
            if matcher and matcher.lower() in app_name:
                return True
        return False


class GestureRegistry:
    """
    Manages all gesture definitions.
    
    Loading order:
    1. System gestures (immutable defaults)
    2. Custom user-defined gestures
    3. Active profile overrides (can change thresholds/actions, not add system gestures)
    
    Usage:
        registry = GestureRegistry()
        registry.load()
        gestures = registry.get_all_enabled()
        g = registry.get_by_id("pinch_click")
    """

    def __init__(self):
        self._system: Dict[str, GestureDefinition] = {}
        self._custom: Dict[str, GestureDefinition] = {}
        self._profiles: Dict[str, GestureProfile] = {}
        self._active_profile_id: str = "default"
        self._loaded = False

    def load(self) -> bool:
        """Load all gesture definitions from disk."""
        ok = True
        ok &= self._load_system_gestures()
        self._load_custom_gestures()
        self._load_profiles()
        self._loaded = True
        logger.info(
            f"GestureRegistry loaded: {len(self._system)} system, "
            f"{len(self._custom)} custom, profile={self._active_profile_id}"
        )
        return ok

    def _load_system_gestures(self) -> bool:
        if not os.path.exists(SYSTEM_GESTURES_FILE):
            logger.warning(f"System gestures file not found: {SYSTEM_GESTURES_FILE}")
            return False
        try:
            with open(SYSTEM_GESTURES_FILE) as f:
                data = json.load(f)
            for g in data.get("gestures", []):
                defn = GestureDefinition.from_dict(g)
                self._system[defn.id] = defn
            return True
        except Exception as e:
            logger.error(f"Failed to load system gestures: {e}")
            return False

    def _load_custom_gestures(self):
        os.makedirs(CUSTOM_DIR, exist_ok=True)
        custom_file = os.path.join(CUSTOM_DIR, "custom_gestures.json")
        if not os.path.exists(custom_file):
            return
        try:
            with open(custom_file) as f:
                data = json.load(f)
            for g in data.get("gestures", []):
                defn = GestureDefinition.from_dict(g)
                self._custom[defn.id] = defn
        except Exception as e:
            logger.warning(f"Failed to load custom gestures: {e}")

    def _load_profiles(self):
        os.makedirs(PROFILES_DIR, exist_ok=True)
        profiles_file = os.path.join(PROFILES_DIR, "profiles.json")
        if not os.path.exists(profiles_file):
            # Create default profile
            default = {"profiles": [{"id": "default", "name": "Default", "active": True, "gesture_overrides": {}}]}
            with open(profiles_file, "w") as f:
                json.dump(default, f, indent=2)
            self._profiles["default"] = GestureProfile("default", "Default", True)
            return

        try:
            with open(profiles_file) as f:
                data = json.load(f)
            for p in data.get("profiles", []):
                profile = GestureProfile(
                    id=p["id"],
                    name=p["name"],
                    active=p.get("active", False),
                    app_matchers=p.get("app_matchers", []),
                    gesture_overrides=p.get("gesture_overrides", {}),
                )
                self._profiles[profile.id] = profile
                if profile.active:
                    self._active_profile_id = profile.id
        except Exception as e:
            logger.warning(f"Failed to load profiles: {e}")

    def get_all(self) -> List[GestureDefinition]:
        """All gestures (system + custom), with active profile overrides applied."""
        result = {}
        # System first
        for gid, g in self._system.items():
            result[gid] = g
        # Custom overrides
        for gid, g in self._custom.items():
            result[gid] = g
        # Apply profile overrides (can modify thresholds/action of existing gestures)
        if self._active_profile_id in self._profiles:
            profile = self._profiles[self._active_profile_id]
            for gid, overrides in profile.gesture_overrides.items():
                if gid in result:
                    g = result[gid]
                    # Apply overrides as a new dataclass instance
                    d = g.to_dict()
                    d.update(overrides)
                    result[gid] = GestureDefinition.from_dict(d)
        return list(result.values())

    # ── Profile management ────────────────────────────────────────────
    def get_profiles(self) -> List[GestureProfile]:
        return list(self._profiles.values())

    def get_profile(self, profile_id: str) -> Optional[GestureProfile]:
        return self._profiles.get(profile_id)

    def set_active_profile(self, profile_id: str) -> bool:
        """Activate a profile. Persists active flag to profiles.json."""
        if profile_id not in self._profiles:
            logger.warning(f"Profile not found: {profile_id}")
            return False
        for p in self._profiles.values():
            p.active = (p.id == profile_id)
        self._active_profile_id = profile_id
        self._save_profiles()
        logger.info(f"Active profile set to: {profile_id}")
        return True

    def add_profile(self, profile: GestureProfile) -> bool:
        if profile.id in self._profiles:
            return False
        self._profiles[profile.id] = profile
        self._save_profiles()
        return True

    def remove_profile(self, profile_id: str) -> bool:
        if profile_id not in self._profiles or profile_id == "default":
            return False
        del self._profiles[profile_id]
        if self._active_profile_id == profile_id:
            self.set_active_profile("default")
        self._save_profiles()
        return True

    def update_profile(self, profile: GestureProfile) -> bool:
        if profile.id not in self._profiles:
            return False
        self._profiles[profile.id] = profile
        if profile.active:
            self._active_profile_id = profile.id
        self._save_profiles()
        return True

    def _save_profiles(self):
        os.makedirs(PROFILES_DIR, exist_ok=True)
        profiles_file = os.path.join(PROFILES_DIR, "profiles.json")
        data = {"profiles": [p.to_dict() for p in self._profiles.values()]}
        with open(profiles_file, "w") as f:
            json.dump(data, f, indent=2)

    def get_profile_for_app(self, app_name: str) -> Optional[GestureProfile]:
        """Find the best matching app profile for a foreground app (excluding
        the default profile, which is always the fallback)."""
        if not app_name:
            return None
        app_name = app_name.lower()
        # Most specific matcher wins — prefer profiles declared last (longest match).
        best = None
        best_len = 0
        for profile in self._profiles.values():
            if profile.id == "default":
                continue
            for matcher in profile.app_matchers:
                m = matcher.lower()
                if m and m in app_name and len(m) > best_len:
                    best = profile
                    best_len = len(m)
        return best

    def get_all_enabled(self) -> List[GestureDefinition]:
        return [g for g in self.get_all() if g.enabled]

    def get_by_id(self, gesture_id: str) -> Optional[GestureDefinition]:
        for g in self.get_all():
            if g.id == gesture_id:
                return g
        return None

    def enable(self, gesture_id: str):
        """Enable a gesture (applies to custom, not system)."""
        if gesture_id in self._custom:
            self._custom[gesture_id].enabled = True
            self._save_custom()

    def disable(self, gesture_id: str):
        """Disable a gesture (system gestures cannot be fully disabled for safety)."""
        if gesture_id in self._custom:
            self._custom[gesture_id].enabled = False
            self._save_custom()

    def add_custom(self, gesture: GestureDefinition):
        """Add a custom user-defined gesture."""
        gesture.system = False
        self._custom[gesture.id] = gesture
        self._save_custom()
        logger.info(f"Custom gesture added: {gesture.id}")

    def _save_custom(self):
        os.makedirs(CUSTOM_DIR, exist_ok=True)
        custom_file = os.path.join(CUSTOM_DIR, "custom_gestures.json")
        data = {"gestures": [g.to_dict() for g in self._custom.values()]}
        with open(custom_file, "w") as f:
            json.dump(data, f, indent=2)

    def get_threshold(self, gesture_id: str, key: str, default: float = 0.0) -> float:
        """Convenient threshold accessor."""
        g = self.get_by_id(gesture_id)
        if g is None:
            return default
        return g.thresholds.get(key, default)

    def get_all_for_ipc(self) -> list:
        """Return gesture list in IPC-friendly format."""
        return [g.to_dict() for g in self.get_all()]

    @property
    def active_profile(self) -> Optional[GestureProfile]:
        return self._profiles.get(self._active_profile_id)
