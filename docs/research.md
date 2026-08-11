# AirOS Research Notes

**Date:** 2026-08-11  
**Author:** AirOS Engineering Team  
**Status:** Active — Updated per build stages

---

## 1. Environment Assessment

### Hardware
- **GPU:** NVIDIA RTX 4050 Laptop GPU — 6141 MiB VRAM, Driver 610.88
- **OS:** Windows 11 Home Single Language (Build 26200)

### Software Environment
- **Python available:** 3.14.7 (system default), 3.11.15 (via Astral/uv), 3.13 (Store)
- **Node.js:** v26.7.0  |  **npm:** 11.19.0

> **CRITICAL FINDING:** MediaPipe does NOT support Python 3.14. Official support covers Python 3.9–3.12 only.  
> **Resolution:** All Python engine code uses the Python 3.11.15 venv at `air-os/venv/`.

---

## 2. MediaPipe Hand Tracking

### API: Tasks SDK (Recommended over legacy mp.solutions)
- `HandLandmarker` — 21 keypoints per hand, normalized [0,1]
- Three running modes: IMAGE, VIDEO, LIVE_STREAM
- `LIVE_STREAM` mode: async callback — does NOT block capture loop ← critical for latency

### Performance Characteristics
- Inference time: ~10–20ms on RTX 4050
- Palm detector only re-runs when tracking is lost (major CPU saving)
- Optimal hand distance: 30–80cm from camera

### Limitations (honest assessment)
- No depth from RGB cam. Depth inferred from hand width — inaccurate.
- Tracking loss under fast movement, self-occlusion, poor lighting (<200 lux).
- MediaPipe built-in GestureRecognizer gestures insufficient for AirOS — use HandLandmarker + custom logic.

---

## 3. OpenCV Camera Capture

### Backend
Use `cv2.CAP_DSHOW` (DirectShow) for lower latency on Windows:
```python
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
```

### Frame Queue Strategy
Latest-frame only. If processing falls behind, discard stale frames. NEWEST FRAME > PROCESS EVERY FRAME.

---

## 4. Windows Input: SendInput via ctypes

### Why SendInput over PyAutoGUI
- PyAutoGUI uses `SetCursorPos` — not a real input event.
- SendInput injects at hardware abstraction layer — reliable, works in more apps.

### Strategy
Use ABSOLUTE positioning (`MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE`) mapped to [0,65535].
Handle return value (number of events injected) and log failures.

---

## 5. Temporal Filtering: One Euro Filter

### Problem
Raw landmarks jitter ±5–15px with stationary hand.

### Solution: One Euro Filter (CHOSEN)
- Designed for HCI input — adapts cutoff based on velocity.
- Low motion = low cutoff (stable) | Fast motion = high cutoff (responsive).
- ~50 lines Python, MIT licensed.
- Reference: Casiez et al., 2012.

### Rejected Alternatives
- EMA: fixed alpha = always a compromise.
- Kalman: overkill, complex tuning.

---

## 6. Gesture Recognition Strategy

### Core gestures: Geometric features (fast, <2ms)
- **Pinch:** Distance between tip(4) and tip(8) normalized by wrist-to-MCP
- **Finger extension:** Tip Y vs MCP Y (image space)
- **Velocity/direction:** First-order difference of wrist position
- **Swipe:** Displacement + velocity threshold over time window
- **Open palm:** All 5 tips extended

### Temporal Confirmation (mandatory)
Never act on single frame. Confirmation window: 3–5 frames (~100–166ms @ 30fps).

### Custom Gestures (Stage 12+)
k-NN or template matching on normalized landmark sequences. Local only. No LLM. No cloud.

---

## 7. IPC Architecture

### Decision: WebSocket (asyncio)
- Python asyncio server: `localhost:7890`
- Engine → UI: telemetry at 10 Hz (every 100ms)
- UI → Engine: control commands (start/stop/pause/calibrate)
- Completely decoupled from real-time pipeline (separate thread)

---

## 8. Existing Projects Review

### MotionInput (UCL)
- Modular Python + Win32 API + MediaPipe
- **Useful patterns:** Modular design, gesture confirmation
- **License:** Check before copying any code

### Common Tutorial Patterns (DO NOT COPY)
1. Map raw landmark to screen coordinate directly (no smoothing)
2. Trigger action from single frame
3. Block UI in real-time loop
4. Grow unbounded frame queue

---

## 9. Technical Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Tracking loss (fast movement) | Medium | Predict during loss, re-detect |
| Python GIL bottleneck | High | multiprocessing for engine vs UI |
| False activations | High | Temporal confirmation + dead zones |
| Cursor jitter | High | One Euro Filter |
| Air typing accuracy | Very High | Limited to short text, NOT touch-typing speed |
| Python 3.14 incompatibility | RESOLVED | Use venv Python 3.11.15 |

---

## 10. Licensing

| Component | License |
|-----------|---------|
| MediaPipe | Apache 2.0 |
| OpenCV | Apache 2.0 |
| NumPy | BSD |
| Electron | MIT |
| React | MIT |
| websockets | BSD |
| psutil | BSD |
| One Euro Filter | MIT |

No licensing blockers.

---

## 11. Performance Model (Predicted — to be validated with measurements)

| Stage | Expected |
|-------|----------|
| Camera capture | 5–15ms |
| MediaPipe inference | 10–20ms |
| Landmark processing | <1ms |
| One Euro Filter | <0.1ms |
| Gesture recognition | <2ms |
| State machine | <0.5ms |
| SendInput | <1ms |
| **Total predicted** | **~20–40ms** |

All numbers will be replaced with measured values after Stage 2.
