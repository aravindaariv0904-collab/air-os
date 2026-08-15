"""
AirOS — Main Entry Point
Starts the engine with IPC server, lifecycle manager, and safety hotkey.

Usage (from air-os directory):
    python run_engine.py [--no-ipc] [--debug]
"""

import sys
import os
import logging
import argparse
import threading
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from config.paths import get_logs_dir
from engine.lifecycle import get_lifecycle_manager, EngineState


def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    import sys, io
    logs_dir = get_logs_dir()
    os.makedirs(logs_dir, exist_ok=True)
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(
                io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
                if hasattr(sys.stdout, 'buffer') else sys.stdout
            ),
            logging.FileHandler(
                os.path.join(logs_dir, "engine.log"),
                encoding="utf-8",
            ),
        ],
    )


def main():
    parser = argparse.ArgumentParser(description="AirOS Engine")
    parser.add_argument("--no-ipc", action="store_true", help="Disable IPC server")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--camera", type=int, default=0, help="Camera index")
    parser.add_argument("--max-frames", type=int, default=None,
                        help="Exit after this many pipeline frames (smoke tests)")
    args = parser.parse_args()

    setup_logging(args.debug)
    logger = logging.getLogger("airos")

    logger.info("="*50)
    logger.info("  AirOS Engine v0.1.0")
    logger.info("="*50)

    from engine.main import AirOSEngine
    from ipc.server import IPCServer

    lifecycle = get_lifecycle_manager()

    ipc = None
    if not args.no_ipc:
        def on_command(command: str, data: dict):
            logger.info(f"Command received: {command}")
            payload = data.get("payload", data) if isinstance(data.get("payload"), dict) else data

            if command == "stop":
                engine.stop()
            elif command == "pause":
                engine.pause()
            elif command == "resume":
                engine.resume()
            elif command == "calibrate":
                engine.start_calibration()
            elif command == "calibrate_cancel":
                engine.stop_calibration(apply=False)
            elif command == "calibrate_finish":
                engine.stop_calibration(apply=True)
            elif command == "gesture_start_recording":
                engine.studio_start_recording()
            elif command == "gesture_finish_recording":
                rec = engine.studio_finish_recording(payload.get("name", "Custom Gesture"))
                if ipc and rec:
                    ipc.push_message({"type": "gesture_recorded", "template": rec})
            elif command == "gesture_cancel_recording":
                engine.studio_cancel_recording()
            elif command == "gesture_list":
                result = engine.studio_list()
                if ipc:
                    ipc.push_message({"type": "gesture_list", "templates": result})
            elif command == "gesture_delete":
                engine.studio_delete(payload.get("id", ""))
                if ipc:
                    ipc.push_message({"type": "gesture_list", "templates": engine.studio_list()})
            elif command == "gesture_rename":
                engine.studio_rename(payload.get("id", ""), payload.get("name", ""))
                if ipc:
                    ipc.push_message({"type": "gesture_list", "templates": engine.studio_list()})
            elif command == "gesture_set_action":
                engine.studio_set_action(payload.get("id", ""), payload.get("action", ""))
                if ipc:
                    ipc.push_message({"type": "gesture_list", "templates": engine.studio_list()})
            elif command == "profile_set":
                engine.profile_set(payload.get("id", ""))
            elif command == "profile_list":
                if ipc:
                    ipc.push_message({
                        "type": "profile_list",
                        "profiles": engine.profile_list(),
                        "current": engine.profile_current(),
                    })
            elif command == "profile_set_override":
                engine.profile_set_override(
                    payload.get("profile_id", ""),
                    payload.get("gesture_id", ""),
                    payload.get("override", {}),
                )
            elif command == "settings_update":
                updated = engine.settings_update(payload.get("settings", payload))
                if ipc:
                    ipc.push_message({"type": "settings_data", "settings": updated})
            elif command == "settings_get":
                cfg = engine.settings_get()
                if ipc:
                    ipc.push_message({"type": "settings_data", "settings": cfg})

        ipc = IPCServer(on_command=on_command)

        def on_lifecycle_change(state: EngineState, error_msg: str = None):
            if ipc:
                ipc.push_message({
                    "type": "engine_state",
                    "state": state.value,
                    "error": error_msg,
                })

        lifecycle.add_state_callback(on_lifecycle_change)
        ipc.start()

    def on_telemetry(telemetry):
        if ipc:
            ipc.push_telemetry(telemetry.to_dict())

    engine = AirOSEngine(telemetry_callback=on_telemetry)
    if args.max_frames is not None:
        engine._max_frames = args.max_frames

    def setup_hotkey():
        try:
            from pynput import keyboard as kb

            def on_hotkey():
                logger.warning("SAFETY HOTKEY ACTIVATED — stopping engine")
                engine.stop()
                if ipc:
                    ipc.stop()
                sys.exit(0)

            with kb.GlobalHotKeys({"<ctrl>+<alt>+a": on_hotkey}) as hotkey_listener:
                hotkey_listener.join()
        except Exception as e:
            logger.warning(f"Global hotkey failed: {e}")

    hotkey_thread = threading.Thread(target=setup_hotkey, daemon=True, name="HotkeyListener")
    hotkey_thread.start()
    logger.info("Safety hotkey: Ctrl+Alt+A to stop")

    try:
        success = engine.start()
        if not success:
            logger.error("Engine failed to start")
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        engine.stop()
        if ipc:
            ipc.stop()
        logger.info("AirOS shutdown complete")


if __name__ == "__main__":
    main()
