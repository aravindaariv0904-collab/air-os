"""
AirOS — Authoritative Configuration Manager
Typed, versioned configuration model with schema validation, atomic writes,
runtime updates, and persistence under %APPDATA%/AirOS/
"""

import json
import os
import shutil
import tempfile
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional

from config.paths import get_app_data_dir, get_config_file, get_calibration_file

logger = logging.getLogger(__name__)

CONFIG_VERSION = "1.0"


@dataclass
class CursorConfigModel:
    region_left: float = 0.10
    region_right: float = 0.90
    region_top: float = 0.10
    region_bottom: float = 0.85
    dead_zone: float = 0.008
    sensitivity: float = 1.0
    smoothing_min_cutoff: float = 1.2
    smoothing_beta: float = 0.008
    smoothing_d_cutoff: float = 1.0
    virtual_left: int = 0
    virtual_top: int = 0
    screen_width: int = 0
    screen_height: int = 0

    def validate(self):
        self.region_left = max(0.0, min(0.45, float(self.region_left)))
        self.region_right = max(0.55, min(1.0, float(self.region_right)))
        self.region_top = max(0.0, min(0.45, float(self.region_top)))
        self.region_bottom = max(0.55, min(1.0, float(self.region_bottom)))
        self.dead_zone = max(0.0, min(0.05, float(self.dead_zone)))
        self.sensitivity = max(0.2, min(3.0, float(self.sensitivity)))
        self.smoothing_min_cutoff = max(0.1, min(5.0, float(self.smoothing_min_cutoff)))
        self.smoothing_beta = max(0.001, min(0.1, float(self.smoothing_beta)))


@dataclass
class GestureConfigModel:
    pinch_threshold: float = 0.30
    release_threshold: float = 0.45
    scroll_speed: int = 3
    scroll_velocity_threshold: float = 0.15
    swipe_displacement_threshold: float = 0.18
    swipe_velocity_threshold: float = 0.35
    air_tap_threshold: float = 0.04
    open_palm_hold_sec: float = 0.8
    two_hand_hold_sec: float = 1.5
    preferred_hand: str = "right"

    def validate(self):
        self.pinch_threshold = max(0.10, min(0.50, float(self.pinch_threshold)))
        self.release_threshold = max(self.pinch_threshold + 0.05, min(0.60, float(self.release_threshold)))
        self.scroll_speed = max(1, min(10, int(self.scroll_speed)))
        self.scroll_velocity_threshold = max(0.05, min(0.50, float(self.scroll_velocity_threshold)))
        self.swipe_displacement_threshold = max(0.05, min(0.40, float(self.swipe_displacement_threshold)))
        self.swipe_velocity_threshold = max(0.10, min(1.00, float(self.swipe_velocity_threshold)))
        if self.preferred_hand not in ("left", "right"):
            self.preferred_hand = "right"


@dataclass
class SystemConfigModel:
    start_minimized: bool = False
    start_engine_on_launch: bool = True
    debug_logging: bool = False
    target_loop_fps: int = 60
    camera_index: int = 0
    camera_width: int = 640
    camera_height: int = 480
    ipc_port: int = 7890

    def validate(self):
        self.target_loop_fps = max(30, min(120, int(self.target_loop_fps)))
        self.camera_index = max(0, int(self.camera_index))


@dataclass
class EyesConfigModel:
    """Eye-tracking / blink gesture configuration."""
    enabled: bool = True
    triple_blink_action: str = "screenshot"
    ear_threshold: float = 0.21
    min_closed_ms: float = 40.0
    max_closed_ms: float = 400.0
    cooldown_ms: float = 4000.0

    def validate(self):
        self.ear_threshold = max(0.05, min(0.45, float(self.ear_threshold)))
        self.min_closed_ms = max(10.0, min(500.0, float(self.min_closed_ms)))
        self.max_closed_ms = max(50.0, min(1000.0, float(self.max_closed_ms)))
        self.cooldown_ms = max(500.0, min(30000.0, float(self.cooldown_ms)))


@dataclass
class VoiceConfigModel:
    """Local voice assistant configuration (Vosk + pyttsx3, fully offline)."""
    enabled: bool = False
    wake_word: str = "jarvis"
    command_timeout_ms: int = 7000
    silence_timeout_ms: int = 1400
    tts_enabled: bool = True
    wake_sensitivity: float = 0.6

    def validate(self):
        self.wake_word = (self.wake_word or "jarvis").strip().lower()
        self.command_timeout_ms = max(2000, min(15000, int(self.command_timeout_ms)))
        self.silence_timeout_ms = max(400, min(5000, int(self.silence_timeout_ms)))
        self.wake_sensitivity = max(0.1, min(1.0, float(self.wake_sensitivity)))


@dataclass
class AppConfigModel:
    version: str = CONFIG_VERSION
    cursor: CursorConfigModel = field(default_factory=CursorConfigModel)
    gestures: GestureConfigModel = field(default_factory=GestureConfigModel)
    system: SystemConfigModel = field(default_factory=SystemConfigModel)
    eyes: EyesConfigModel = field(default_factory=EyesConfigModel)
    voice: VoiceConfigModel = field(default_factory=VoiceConfigModel)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "cursor": asdict(self.cursor),
            "gestures": asdict(self.gestures),
            "system": asdict(self.system),
            "eyes": asdict(self.eyes),
            "voice": asdict(self.voice),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AppConfigModel":
        version = d.get("version", CONFIG_VERSION)
        cursor = CursorConfigModel(**d.get("cursor", {})) if isinstance(d.get("cursor"), dict) else CursorConfigModel()
        gestures = GestureConfigModel(**d.get("gestures", {})) if isinstance(d.get("gestures"), dict) else GestureConfigModel()
        system = SystemConfigModel(**d.get("system", {})) if isinstance(d.get("system"), dict) else SystemConfigModel()
        eyes = EyesConfigModel(**d.get("eyes", {})) if isinstance(d.get("eyes"), dict) else EyesConfigModel()
        voice = VoiceConfigModel(**d.get("voice", {})) if isinstance(d.get("voice"), dict) else VoiceConfigModel()

        cfg = cls(version=version, cursor=cursor, gestures=gestures, system=system,
                  eyes=eyes, voice=voice)
        cfg.validate()
        return cfg

    def validate(self):
        self.cursor.validate()
        self.gestures.validate()
        self.system.validate()
        self.eyes.validate()
        self.voice.validate()


class ConfigManager:
    """Authoritative service for loading, saving, validating, and updating config."""

    def __init__(self, config_file: Optional[str] = None):
        self._config_file = config_file or get_config_file()
        self._config = AppConfigModel()
        self.load()

    @property
    def config(self) -> AppConfigModel:
        return self._config

    def load(self) -> AppConfigModel:
        """Load configuration from APPDATA file if exists, else write defaults."""
        if not os.path.exists(self._config_file):
            logger.info(f"Config file not found at {self._config_file}, creating defaults.")
            self.save()
            return self._config

        try:
            with open(self._config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._config = AppConfigModel.from_dict(data)
            logger.info(f"Loaded configuration from {self._config_file}")
        except Exception as e:
            logger.warning(f"Error reading config file {self._config_file}: {e}. Resetting to defaults.")
            self.reset_defaults()

        return self._config

    def save(self):
        """Atomic write to config file to prevent corruption."""
        self._config.validate()
        dir_name = os.path.dirname(self._config_file)
        os.makedirs(dir_name, exist_ok=True)

        payload = json.dumps(self._config.to_dict(), indent=2)
        temp_fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix="cfg_tmp_", suffix=".json")
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(payload)
            shutil.move(temp_path, self._config_file)
            logger.info(f"Atomically saved config to {self._config_file}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    def reset_defaults(self):
        """Reset configuration to default values and save."""
        self._config = AppConfigModel()
        self.save()

    def update_dict(self, updates: Dict[str, Any]) -> AppConfigModel:
        """Apply patch dictionary to config and save."""
        cur_dict = self._config.to_dict()

        for section in ("cursor", "gestures", "system", "eyes", "voice"):
            if section in updates and isinstance(updates[section], dict):
                cur_dict[section].update(updates[section])

        self._config = AppConfigModel.from_dict(cur_dict)
        self.save()
        return self._config


_global_config_manager: Optional[ConfigManager] = None

def get_config_manager() -> ConfigManager:
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = ConfigManager()
    return _global_config_manager
