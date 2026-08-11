"""
AirOS — Engine smoke test
Boots the full engine (camera + tracking + pipeline) for N frames and exits 0
on clean shutdown. Fails (exit 1) if the engine cannot start or crashes.

Usage (from air-os directory):
    python scripts/smoke_engine.py [--frames 60] [--camera 0]
"""

import os
import sys
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def main():
    parser = argparse.ArgumentParser(description="AirOS engine smoke test")
    parser.add_argument("--frames", type=int, default=60, help="Frames to process")
    parser.add_argument("--camera", type=int, default=0, help="Camera index")
    args = parser.parse_args()

    import logging
    logging.basicConfig(level=logging.WARNING)

    from engine.main import AirOSEngine

    engine = AirOSEngine()
    engine._max_frames = args.frames
    try:
        ok = engine.start()
        if not ok:
            print("SMOKE FAIL: engine failed to start")
            return 1
        print(f"SMOKE PASS: ran {engine._frame_count} frames and shut down cleanly")
        return 0
    except Exception as e:  # pragma: no cover
        print(f"SMOKE FAIL: engine crashed: {e!r}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
