"""
AirOS — Gesture Studio CLI
Record and test custom gestures from the command line, using the live camera.

Usage (from air-os directory):
    python scripts/gesture_studio_cli.py record "Wave" [--frames 40] [--camera 0]
    python scripts/gesture_studio_cli.py list
    python scripts/gesture_studio_cli.py delete <id>
    python scripts/gesture_studio_cli.py rename <id> "New Name"
    python scripts/gesture_studio_cli.py set-action <id> volume_up
    python scripts/gesture_studio_cli.py test [--seconds 5] [--camera 0]

For `record`: perform the gesture in front of the camera while frames are
collected. The engine must NOT be running (only one process may own the camera).
"""

import os
import sys
import time
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import numpy as np

from gestures.recognition.studio import GestureStudio
from input.action_registry import ActionRegistry
from input.windows.send_input import WindowsInputAdapter


def _collect_frames(frames: int, camera_index: int):
    """Collect `frames` landmark arrays from the webcam. Yields (n, landmarks)."""
    from engine.camera.capture import CameraCapture, CameraConfig
    from engine.tracking.hand_tracker import HandTracker, TrackerConfig

    cam = CameraCapture(CameraConfig(
        camera_index=camera_index, width=640, height=480, fps=30,
        use_dshow=True, flip_horizontal=True,
    ))
    tracker = HandTracker(TrackerConfig(
        model_path="assets/models/hand_landmarker.task", num_hands=1,
    ))

    if not tracker.initialize():
        print("HandTracker init failed")
        return
    if not cam.start():
        print("Camera start failed")
        return

    mp_ts = 0
    collected = 0
    try:
        while collected < frames:
            frame, _ = cam.get_frame()
            if frame is None:
                time.sleep(0.001)
                continue
            mp_ts += 1
            tracker.process_frame(frame, mp_ts)
            result = tracker.get_latest_result()
            if result is not None and result.num_hands > 0:
                lm = result.landmarks[0]
                yield collected, lm
                collected += 1
            time.sleep(0.02)
    finally:
        cam.stop()
        tracker.close()


def cmd_record(args):
    studio = GestureStudio()
    if studio.is_recording:
        studio.cancel_recording()
    studio.start_recording()
    print(f"Recording '{args.name}' — perform the gesture now for {args.frames} frames...")
    for n, lm in _collect_frames(args.frames, args.camera):
        studio.record_frame(lm)
        if n % 10 == 0:
            print(f"  captured {n + 1}/{args.frames} frames")
    template = studio.finish_recording(args.name)
    if template is None:
        print("Recording failed — not enough frames captured.")
        return 1
    print(f"Saved gesture '{template.name}' (id={template.id}, "
          f"{template.frame_count} frames, action={template.action})")
    return 0


def cmd_list(_args):
    studio = GestureStudio()
    templates = studio.list_templates()
    if not templates:
        print("No custom gestures recorded.")
        return 0
    print(f"{'ID':<28} {'Name':<20} {'Frames':<7} {'Action':<14} Duration")
    for t in templates:
        print(f"{t['id']:<28} {t['name']:<20} {t['frame_count']:<7} "
              f"{t['action']:<14} {t['duration_s']:.2f}s")
    return 0


def cmd_delete(args):
    studio = GestureStudio()
    if studio.delete_template(args.id):
        print(f"Deleted gesture {args.id}")
        return 0
    print(f"Gesture {args.id} not found")
    return 1


def cmd_rename(args):
    studio = GestureStudio()
    if studio.rename_template(args.id, args.name):
        print(f"Renamed gesture to '{args.name}'")
        return 0
    print(f"Rename failed (id={args.id})")
    return 1


def cmd_set_action(args):
    studio = GestureStudio()
    registry = ActionRegistry(WindowsInputAdapter())
    if not registry.is_valid_action(args.action):
        valid = registry.get_all_actions()
        print(f"Invalid action '{args.action}'. Valid actions: {valid}")
        return 1
    if studio.set_template_action(args.id, args.action):
        print(f"Gesture {args.id} now triggers '{args.action}'")
        return 0
    print(f"Gesture {args.id} not found")
    return 1


def cmd_test(args):
    """Live-match gestures against recorded templates for N seconds."""
    studio = GestureStudio()
    templates = studio.list_templates()
    if not templates:
        print("No custom gestures recorded — record one first.")
        return 1
    print(f"Watching for {args.seconds}s. Perform a gesture to test it...")
    start = time.monotonic()
    last_id = None
    while time.monotonic() - start < args.seconds:
        for _, lm in _collect_frames(1, args.camera):
            ts = time.monotonic()
            matched = studio.match(lm, ts)
            if matched and matched != last_id:
                t = studio.get_template(matched)
                print(f"  MATCH: {t.name} (id={matched}) -> {t.action}")
                last_id = matched
    return 0


def main():
    parser = argparse.ArgumentParser(description="AirOS Gesture Studio CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("record", help="Record a new custom gesture")
    p.add_argument("name")
    p.add_argument("--frames", type=int, default=40)
    p.add_argument("--camera", type=int, default=0)
    p.set_defaults(func=cmd_record)

    sub.add_parser("list", help="List recorded gestures").set_defaults(func=cmd_list)

    p = sub.add_parser("delete", help="Delete a gesture by id")
    p.add_argument("id")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("rename", help="Rename a gesture")
    p.add_argument("id")
    p.add_argument("name")
    p.set_defaults(func=cmd_rename)

    p = sub.add_parser("set-action", help="Assign a safe action to a gesture")
    p.add_argument("id")
    p.add_argument("action")
    p.set_defaults(func=cmd_set_action)

    p = sub.add_parser("test", help="Live-test gestures against recorded templates")
    p.add_argument("--seconds", type=int, default=5)
    p.add_argument("--camera", type=int, default=0)
    p.set_defaults(func=cmd_test)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
