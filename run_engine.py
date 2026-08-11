"""
AirOS — Main Entry Point
Starts the engine with IPC server and safety hotkey.

Usage (from air-os directory):
    python run_engine.py [--no-ipc] [--debug]

The engine runs in the main thread.
The IPC WebSocket server runs in a background thread.
The global hotkey listener runs in a background thread.
"""

import sys
import os
import logging
import argparse
import threading
import time

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)


def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    import sys, io
    # Force UTF-8 on Windows console to handle emoji/arrows in logs
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
                os.path.join(PROJECT_ROOT, "logs", "engine.log"),
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

    # Create logs directory
    os.makedirs(os.path.join(PROJECT_ROOT, "logs"), exist_ok=True)
    setup_logging(args.debug)
    logger = logging.getLogger("airos")

    logger.info("="*50)
    logger.info("  AirOS Engine v0.1.0")
    logger.info("="*50)

    # Import engine
    from engine.main import AirOSEngine
    from ipc.server import IPCServer

    # IPC server
    ipc = None
    if not args.no_ipc:
        def on_command(command: str, data: dict):
            logger.info(f"Command received: {command}")
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
                engine.studio_finish_recording(data.get("name", "Custom Gesture"))
            elif command == "gesture_cancel_recording":
                engine.studio_cancel_recording()
            elif command == "gesture_list":
                result = engine.studio_list()
                if ipc:
                    ipc.push_message({"type": "gesture_list", "templates": result})
            elif command == "gesture_delete":
                engine.studio_delete(data.get("id", ""))
            elif command == "gesture_rename":
                engine.studio_rename(data.get("id", ""), data.get("name", ""))
            elif command == "gesture_set_action":
                engine.studio_set_action(data.get("id", ""), data.get("action", ""))
            elif command == "profile_set":
                engine.profile_set(data.get("id", ""))
            elif command == "profile_list":
                if ipc:
                    ipc.push_message({
                        "type": "profile_list",
                        "profiles": engine.profile_list(),
                        "current": engine.profile_current(),
                    })
            elif command == "profile_set_override":
                engine.profile_set_override(
                    data.get("profile_id", ""),
                    data.get("gesture_id", ""),
                    data.get("override", {}),
                )

        ipc = IPCServer(on_command=on_command)
        ipc.start()

    # Create engine with telemetry callback
    def on_telemetry(telemetry):
        if ipc:
            ipc.push_telemetry(telemetry.to_dict())

    engine = AirOSEngine(telemetry_callback=on_telemetry)
    if args.max_frames is not None:
        engine._max_frames = args.max_frames

    # Safety hotkey: Ctrl+Alt+A → stop
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

    # Start engine (blocking — runs main loop here)
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
