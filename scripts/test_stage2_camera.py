"""
AirOS Stage 2 Diagnostic Test
Tests camera + MediaPipe hand tracking without UI or input injection.

Outputs measured FPS, latency, and landmark detection to console.
Run this FIRST before anything else to verify the pipeline works.

Usage:
    python scripts/test_stage2_camera.py

Controls:
    Q or ESC: quit
    S: show landmark skeleton overlay
    D: toggle debug info display
"""

import sys
import os
import time
import logging
import cv2

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("stage2_test")


def run_stage2_test():
    """Run Stage 2 camera + tracking diagnostic."""
    print("\n" + "="*60)
    print("  AirOS STAGE 2 DIAGNOSTIC — Camera + MediaPipe")
    print("="*60)
    print("Press Q or ESC to quit | S to toggle skeleton | D for debug")
    print()

    # Import components
    from engine.camera.capture import CameraCapture, CameraConfig, detect_cameras
    from engine.tracking.hand_tracker import HandTracker, TrackerConfig
    from engine.landmarks.geometry import (
        landmarks_to_array, is_index_only, normalized_pinch_distance,
        is_open_palm, count_extended_fingers
    )

    # Detect cameras
    print("Detecting cameras...")
    cameras = detect_cameras(max_index=4)
    if not cameras:
        print("ERROR: No cameras detected!")
        return False
    for cam in cameras:
        print(f"  Camera {cam['index']}: {cam['width']}x{cam['height']} @ {cam['fps']} FPS")
    print()

    # Initialize camera
    camera = CameraCapture(CameraConfig(
        camera_index=0,
        width=640,
        height=480,
        fps=30,
        use_dshow=True,
    ))

    # Initialize tracker
    tracker = HandTracker(TrackerConfig(
        model_path=os.path.join(PROJECT_ROOT, "assets/models/hand_landmarker.task"),
    ))

    print("Initializing HandTracker (downloading model if needed)...")
    if not tracker.initialize():
        print("ERROR: Failed to initialize HandTracker!")
        return False
    print("HandTracker initialized OK")
    print()

    print("Starting camera...")
    if not camera.start():
        print("ERROR: Failed to start camera!")
        return False

    # Wait for first frame
    for _ in range(30):
        frame, ts = camera.get_frame()
        if frame is not None:
            break
        time.sleep(0.05)

    if frame is None:
        print("ERROR: No frames received!")
        camera.stop()
        return False

    print(f"Camera active: {frame.shape[1]}x{frame.shape[0]}")
    print()
    print("Pipeline running... show your hand to the camera.")
    print()

    # Stats collection
    frame_times = []
    inference_times = []
    gesture_counts = {"none": 0, "index": 0, "pinch": 0, "palm": 0}
    mp_timestamp = 0
    show_skeleton = True
    show_debug = True
    test_start = time.monotonic()
    last_result = None
    last_print = time.monotonic()

    while True:
        t_loop = time.monotonic()

        # Get frame
        frame, frame_ts = camera.get_frame()
        if frame is None:
            time.sleep(0.001)
            continue

        # Submit to tracker
        mp_timestamp += 1
        tracker.process_frame(frame, mp_timestamp)

        # Get result
        result = tracker.get_latest_result()

        # Draw frame
        display = frame.copy()

        if result and result.num_hands > 0:
            if result.inference_time_ms > 0:
                inference_times.append(result.inference_time_ms)
            
            last_result = result
            landmarks = result.landmarks[0]

            # Gesture classification
            if is_open_palm(landmarks):
                gesture = "OPEN PALM 🖐️"
                gesture_counts["palm"] += 1
            elif is_index_only(landmarks):
                gesture = "INDEX POINTER ☝️"
                gesture_counts["index"] += 1
            else:
                pinch_dist = normalized_pinch_distance(landmarks)
                if pinch_dist < 0.30:
                    gesture = f"PINCH 🤏 ({pinch_dist:.2f})"
                    gesture_counts["pinch"] += 1
                else:
                    gesture_counts["none"] += 1
                    gesture = f"NONE ({count_extended_fingers(landmarks)} fingers)"

            # Draw landmarks
            if show_skeleton:
                h, w = display.shape[:2]
                for i, lm in enumerate(landmarks):
                    px, py = int(lm[0] * w), int(lm[1] * h)
                    color = (0, 255, 0) if i in [4, 8] else (0, 200, 255)
                    cv2.circle(display, (px, py), 4, color, -1)

                # Draw connections (simplified)
                connections = [
                    (0, 5), (5, 9), (9, 13), (13, 17), (17, 0),  # Palm
                    (5, 6), (6, 7), (7, 8),   # Index
                    (0, 1), (1, 2), (2, 3), (3, 4),  # Thumb
                ]
                for a, b in connections:
                    ax = int(landmarks[a][0] * w)
                    ay = int(landmarks[a][1] * h)
                    bx = int(landmarks[b][0] * w)
                    by = int(landmarks[b][1] * h)
                    cv2.line(display, (ax, ay), (bx, by), (100, 255, 100), 1)

            # Display gesture
            cv2.putText(display, gesture, (10, 35), cv2.FONT_HERSHEY_SIMPLEX,
                       0.7, (0, 255, 0), 2)
            cv2.putText(display, f"Hands: {result.num_hands}", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        else:
            cv2.putText(display, "No hands detected", (10, 35),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 255), 2)

        # Performance overlay
        cam_metrics = camera.metrics
        if show_debug:
            inf_avg = sum(inference_times[-30:]) / max(len(inference_times[-30:]), 1)
            cv2.putText(display, f"FPS: {cam_metrics.actual_fps:.1f} (avg {cam_metrics.avg_fps:.1f})",
                       (10, display.shape[0]-80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 255, 200), 1)
            cv2.putText(display, f"Capture: {cam_metrics.capture_time_ms:.1f}ms",
                       (10, display.shape[0]-60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 255, 200), 1)
            cv2.putText(display, f"Inference: {inf_avg:.1f}ms",
                       (10, display.shape[0]-40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 255, 200), 1)
            cv2.putText(display, f"Dropped: {cam_metrics.dropped_frames}",
                       (10, display.shape[0]-20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 200, 255), 1)
            cv2.putText(display, "AirOS Stage 2 Test",
                       (display.shape[1]-200, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

        cv2.imshow("AirOS Stage 2 — Camera + Tracking", display)

        # Print stats every 3 seconds
        if time.monotonic() - last_print >= 3.0:
            duration = time.monotonic() - test_start
            inf_avg = sum(inference_times) / max(len(inference_times), 1)
            inf_max = max(inference_times) if inference_times else 0
            print(f"[{duration:.0f}s] "
                  f"FPS={cam_metrics.actual_fps:.1f}/{cam_metrics.avg_fps:.1f} "
                  f"| Capture={cam_metrics.capture_time_ms:.1f}ms "
                  f"| Inference avg={inf_avg:.1f}ms max={inf_max:.1f}ms "
                  f"| Dropped={cam_metrics.dropped_frames}")
            last_print = time.monotonic()

        # Loop timing
        frame_times.append(time.monotonic() - t_loop)

        # Key handling
        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):  # Q or ESC
            break
        elif key == ord('s'):
            show_skeleton = not show_skeleton
        elif key == ord('d'):
            show_debug = not show_debug

    # Final report
    cv2.destroyAllWindows()
    camera.stop()
    tracker.close()

    print("\n" + "="*60)
    print("  STAGE 2 TEST RESULTS")
    print("="*60)
    print(f"Test duration: {time.monotonic() - test_start:.1f}s")
    print(f"Camera FPS (final): {camera.metrics.actual_fps:.1f}")
    print(f"Camera FPS (avg): {camera.metrics.avg_fps:.1f}")
    print(f"Camera FPS (min): {camera.metrics.min_fps:.1f}")
    print(f"Dropped frames: {camera.metrics.dropped_frames}")
    print(f"Capture time: {camera.metrics.capture_time_ms:.2f}ms")
    if inference_times:
        print(f"Inference avg: {sum(inference_times)/len(inference_times):.2f}ms")
        print(f"Inference max: {max(inference_times):.2f}ms")
        print(f"Inference min: {min(inference_times):.2f}ms")
    else:
        print("Inference: no hands detected during test")
    print(f"Gesture breakdown: {gesture_counts}")

    # Pass/Fail criteria
    print()
    print("PASS/FAIL:")
    fps_ok = camera.metrics.avg_fps >= 25.0
    print(f"  FPS >= 25:    {'✅ PASS' if fps_ok else '❌ FAIL'} ({camera.metrics.avg_fps:.1f})")
    inf_ok = (sum(inference_times)/max(len(inference_times),1)) < 50
    print(f"  Inference < 50ms: {'✅ PASS' if inf_ok else '❌ FAIL'} ({sum(inference_times)/max(len(inference_times),1):.1f}ms)")
    
    print()
    return fps_ok and inf_ok


if __name__ == "__main__":
    success = run_stage2_test()
    sys.exit(0 if success else 1)
