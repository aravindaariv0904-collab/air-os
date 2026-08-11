"""Minimal repro: capture thread + MediaPipe async, mirroring engine main loop."""
import sys, os, time, logging
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
logging.basicConfig(level=logging.INFO)

from engine.camera.capture import CameraCapture, CameraConfig
from engine.tracking.hand_tracker import HandTracker, TrackerConfig

camera = CameraCapture(CameraConfig(camera_index=0, width=640, height=480, fps=30, use_dshow=True))
tracker = HandTracker(TrackerConfig(model_path=os.path.join(PROJECT_ROOT, "assets/models/hand_landmarker.task")))

print("Init tracker:", tracker.initialize())
print("Start camera:", camera.start())

mp_ts = 0
ok = 0
fail = 0
t0 = time.monotonic()
while time.monotonic() - t0 < 8.0:
    frame, _ = camera.get_frame()
    if frame is None:
        time.sleep(0.002)
        continue
    mp_ts += 1
    tracker.process_frame(frame, mp_ts)
    r = tracker.get_latest_result()
    time.sleep(0.002)

print(f"Camera metrics: avg_fps={camera.metrics.avg_fps:.1f} dropped={camera.metrics.dropped_frames}")
camera.stop()
tracker.close()
print("done")
