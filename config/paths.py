"""
AirOS — Path Configuration Helper
Manages application data paths in %APPDATA%/AirOS as per Windows standards.
"""

import os
import sys

def get_app_data_dir() -> str:
    """Return the absolute path to the user application data directory."""
    if sys.platform == "win32":
        base_dir = os.environ.get("APPDATA")
        if not base_dir:
            base_dir = os.path.expanduser("~")
        app_dir = os.path.join(base_dir, "AirOS")
    else:
        app_dir = os.path.expanduser("~/.airos")

    os.makedirs(app_dir, exist_ok=True)
    os.makedirs(os.path.join(app_dir, "gestures"), exist_ok=True)
    os.makedirs(os.path.join(app_dir, "profiles"), exist_ok=True)
    os.makedirs(os.path.join(app_dir, "logs"), exist_ok=True)
    return app_dir

def get_config_file() -> str:
    return os.path.join(get_app_data_dir(), "config.json")

def get_calibration_file() -> str:
    return os.path.join(get_app_data_dir(), "calibration.json")

def get_gestures_dir() -> str:
    return os.path.join(get_app_data_dir(), "gestures")

def get_profiles_dir() -> str:
    return os.path.join(get_app_data_dir(), "profiles")

def get_logs_dir() -> str:
    return os.path.join(get_app_data_dir(), "logs")
