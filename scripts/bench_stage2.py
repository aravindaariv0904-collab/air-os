"""
AirOS Stage 2 Headless Test — runs without a display window.
Tests camera + MediaPipe for 10 seconds and prints metrics.
"""
import sys, os, time, logging
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
logging.basicConfig(level=logging.WARNING)

from engine.camera.capture import CameraCapture, CameraConfig, detect_cameras
from engine.tracking.hand_tracker import HandTracker, TrackerConfig
from engine.landmarks.geometry import (
    is_index_only, normalized_pinch_distance, is_open_palm
)

print("=== AirOS Stage 2 Headless Benchmark ===")
print()

# Detect cameras
cameras = detect_cameras(4)
print(f"Cameras detected: {len(cameras)}")
for c in cameras:
    print(f"  Camera {c['index']}: {c['width']}x{c['height']} @ {c['fps']} FPS")

# Init
camera = CameraCapture(CameraConfig(camera_index=0, width=640, height=480, fps=30, use_dshow=True))
tracker = HandTracker(TrackerConfig(
    model_path=os.path.join(PROJECT_ROOT, "assets/models/hand_landmarker.task")
))

print()
print("Initializing HandTracker...")
ok = tracker.initialize()
print(f"HandTracker: {'OK' if ok else 'FAILED'}")
if not ok:
    sys.exit(1)

print("Starting camera...")
ok = camera.start()
print(f"Camera: {'OK' if ok else 'FAILED'}")
if not ok:
    sys.exit(1)

# Wait for first frame
for _ in range(50):
    f, _, _ = camera.get_frame()
    if f is not None:
        break
    time.sleep(0.05)

print(f"Frame size: {f.shape[1]}x{f.shape[0]}" if f is not None else "No frame!")
print()
print("Running 10 second benchmark...")

mp_ts = 0
inference_times = []
test_start = time.monotonic()
frames_processed = 0

while time.monotonic() - test_start < 10.0:
    frame, _, _ = camera.get_frame()
    if frame is None:
        time.sleep(0.001)
        continue
    mp_ts += 1
    tracker.process_frame(frame, mp_ts)
    result = tracker.get_latest_result()
    if result and result.inference_time_ms > 0:
        inference_times.append(result.inference_time_ms)
    frames_processed += 1
    time.sleep(0.001)

elapsed = time.monotonic() - test_start
cam = camera.metrics

print()
print("=== STAGE 2 BENCHMARK RESULTS ===")
print(f"Duration:          {elapsed:.1f}s")
print(f"Frames processed:  {frames_processed}")
print(f"Camera FPS (avg):  {cam.avg_fps:.1f}")
print(f"Camera FPS (min):  {cam.min_fps:.1f}")
print(f"Capture time:      {cam.capture_time_ms:.2f}ms")
print(f"Dropped frames:    {cam.dropped_frames}")
if inference_times:
    avg_inf = sum(inference_times)/len(inference_times)
    print(f"Inference avg:     {avg_inf:.2f}ms")
    print(f"Inference max:     {max(inference_times):.2f}ms")
    print(f"Inference min:     {min(inference_times):.2f}ms")
    print(f"Inference samples: {len(inference_times)}")
    fps_ok = cam.avg_fps >= 25.0
    inf_ok = avg_inf < 50.0
    print()
    print(f"FPS >= 25:        {'PASS' if fps_ok else 'FAIL'} ({cam.avg_fps:.1f})")
    print(f"Inference < 50ms: {'PASS' if inf_ok else 'FAIL'} ({avg_inf:.1f}ms)")
else:
    print("No inference data (no hands in frame — normal for headless)")
    print(f"FPS >= 25:        {'PASS' if cam.avg_fps >= 25 else 'FAIL'} ({cam.avg_fps:.1f})")

camera.stop()
tracker.close()
print()
print("STAGE 2: COMPLETE")
