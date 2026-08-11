# AirOS — Comprehensive System Audit & Architectural Assessment

**Document ID**: `AUDIT-2026-08-11`  
**Target Environment**: Windows 10/11 (16GB RAM, RTX 4050 Laptop GPU, Integrated DirectShow Webcam)  
**Goal**: Transform current prototype into a reliable, low-latency, packaged Windows Desktop Application.

---

## 1. Current Architecture Overview

```
[ Built-in Webcam ]
        │ (OpenCV DirectShow / CAP_DSHOW, 640x480)
        ▼
[ CameraCapture ] ──── Thread-safe Latest Frame Buffer (Non-blocking)
        │
        ▼
[ HandTracker ] ───── MediaPipe HandLandmarker Tasks API (LIVE_STREAM Async Callback)
        │
        ▼
[ Geometry & Motion ] ── 21-Landmark Processing, One Euro Filter, Velocity/Displacement
        │
        ▼
[ Gesture Detectors ] ── Pinch, Scroll, Swipe, Open Palm, Two-Hand, Gesture Studio Matcher
        │
        ▼
[ State Machine ] ───── InteractionState (IDLE, POINTER, DRAG, SCROLL, SWIPE, PAUSED, CALIBRATION, KEYBOARD)
        │
        ▼
[ Action Registry ] ─── Controlled Action Mappings (Mouse, Keyboard, Navigation, Media)
        │
        ▼
[ Windows Input ] ───── Win32 SendInput (ctypes, <1ms synchronous injection)

    ┌────────────────────────────────────────────────────────────┐
    │ Independent IPC & UI Layer                                 │
    │ Python Engine ──(Async WebSocket :7890)──> Electron/React   │
    └────────────────────────────────────────────────────────────┘
```

---

## 2. Component Status Classification

### A. Working & Validated Components (Passed 81/81 Automated Tests)
1. **One Euro Filter (`engine/filtering/one_euro.py`)**: Mathematically sound dual-cutoff adaptive low-pass filter (prevents jitter at low speed, high responsiveness at high speed).
2. **Landmark Geometry Utilities (`engine/landmarks/geometry.py`)**: 21-point hand geometry calculations, pinch distance, index pointer isolation, and open palm verification.
3. **Win32 Input Adapter (`input/windows/send_input.py`)**: Native `SendInput` binding for mouse clicks, cursor motion, scroll wheel, virtual keypresses, and Unicode text injection.
4. **State Machine (`engine/state/machine.py`)**: 10-state interaction state machine with debouncing and state transitions.
5. **Virtual Keyboard Core (`keyboard/air_tap/tap_detector.py`)**: QWERTY layout grid, key targeting, and Z-axis air-tap detector.
6. **Gesture Studio Core (`gestures/recognition/studio.py`)**: DTW-like landmark sequence recorder, resampler, matcher, and template persistence.
7. **Profile & Registry System (`gestures/profiles/profile_manager.py`)**: Foreground window detection (`GetForegroundWindow`) and application-specific profile lookup.

### B. Incomplete or Broken Components
1. **Frame Result Synchronization (`engine/main.py`)**:
   - `HandTracker.get_latest_result()` returns stale results if MediaPipe hasn't published a new frame result. `engine/main.py` processes duplicate results on consecutive loop ticks, artificially skewing velocity/motion calculations.
2. **Cursor Engine Multi-Monitor & Sensitivity (`input/mouse/cursor.py`)**:
   - Virtual screen bounds detection assumes `virtual_left = 0` and `virtual_top = 0`. Negative origins (monitors positioned left/top of primary screen) result in wrong coordinates and clamping.
   - Sensitivity currently acts as a global scalar on absolute normalized coordinates rather than gain relative to a control reference point.
3. **Latency Instrumentation (`engine/main.py`)**:
   - Loop duration is currently treated as total latency. Intermediate timestamps (`capture_ts`, `submit_ts`, `tracking_result_ts`, `filter_ts`, `input_inject_ts`) and latency percentiles (P50, P95, P99) are unmeasured.
4. **Fixed 30 FPS Loop Throttling (`engine/main.py`)**:
   - `TARGET_LOOP_FPS = 30` forces sleeping after every frame, capping performance artificially even when camera/processing can run faster.
5. **Config & Data Storage Location (`config/`, `gestures/`)**:
   - User profile JSON, calibration profiles, and gesture templates write directly into the repository folder rather than `%APPDATA%\AirOS\`.
6. **Production Packaging (`apps/desktop/electron/main.js`)**:
   - Hardcoded path to `venv/Scripts/python.exe` inside repository root. Inability to run standalone without Python environment installed.

---

## 3. Critical Bugs & Risks

| Category | Issue Description | Impact | Priority |
| :--- | :--- | :--- | :--- |
| **Sync** | Duplicate MediaPipe result processing | Distorts gesture velocity and temporal confirmation | **CRITICAL (P0)** |
| **Display** | Multi-monitor virtual desktop offset unhandled | Cursor fails or jumps when secondary monitor is left/above | **CRITICAL (P0)** |
| **Packaging** | Hardcoded `venv` path in Electron main process | Application fails on standard user laptops without dev setup | **CRITICAL (P0)** |
| **Performance** | Hardcoded 30 FPS sleep loop | Adds latency and caps response rate | **HIGH (P1)** |
| **Storage** | Writes user settings to project source folder | Permission failure when installed to `%ProgramFiles%` | **HIGH (P1)** |
| **Security** | WebSocket server lacks session authentication token | Unauthenticated local web applications could send control commands | **HIGH (P1)** |

---

## 4. Recommended 21-Phase Action Plan

1. **Phase 1: Existing Code Audit** — *[COMPLETED]* Created `docs/current-audit.md`.
2. **Phase 2: Fix Frame & Result Synchronization** — Implement strict monotonically increasing frame IDs and result timestamp validation to drop duplicate inference results.
3. **Phase 3: Fix Latency Instrumentation** — Add microsecond per-stage telemetry (`capture`, `submit`, `tracking`, `filtering`, `gesture`, `injection`) and P50/P95/P99 latency calculations.
4. **Phase 4: Fix Cursor & Windows Multi-Monitor Input** — Support negative `SM_XVIRTUALSCREEN`/`SM_YVIRTUALSCREEN` bounds and relative gain sensitivity mapping.
5. **Phase 5: Fix Pinch, Click, & Drag** — Implement temporal pinch approach/confirm/release pipeline and prevent conflicting gestures during drag.
6. **Phase 6: Fix Scroll & Swipe** — Implement velocity-proportional relative scroll and directional displacement swipe filtering with proper cooldowns.
7. **Phase 7: Fix Gesture Arbitration & State Machine** — Centralize gesture arbitration with strict safety priority hierarchy (Emergency Stop > Pause > Calibration > Drag > Click > Nav > Pointer).
8. **Phase 8: Complete Guided Calibration** — Interactive step verification (Camera -> Positioning -> Range -> Pinch -> Palm) requiring explicit physical action confirmation.
9. **Phase 9: Complete Gesture Studio Integration** — Enable recording real live hand landmarks from UI with normalized multi-example templates.
10. **Phase 10: Complete Gesture Conflict Detection** — Compare new custom gesture landmarks against system & profile gestures to prevent overlapping triggers.
11. **Phase 11: Complete Application-Specific Profiles** — Allow app-specific profiles (Chrome, VS Code, PowerPoint, Media) with JSON schema validation.
12. **Phase 12: Complete Virtual Keyboard & Air-Tap** — Connect virtual keyboard overlay to active state with debounced Z-axis air-tap key injection.
13. **Phase 13: Connect Dashboard to Real Telemetry** — Ensure all UI counters, charts, and toggles display real live metrics.
14. **Phase 14: Fix Settings & Configuration Persistence** — Move configuration storage to `%APPDATA%\AirOS\`.
15. **Phase 15: Implement Production Python Engine Packaging** — Build standalone `AirOSEngine.exe` via PyInstaller bundling Python runtime, OpenCV, NumPy, MediaPipe model, and DLLs.
16. **Phase 16: Implement Production Electron Packaging** — Configure `electron-builder` to bundle `AirOSEngine.exe` into a single standalone installer (`AirOS_Setup.exe`).
17. **Phase 17: Installation & Execution Verification** — Test installation, startup diagnostics, and clean running on Windows without developer tools.
18. **Phase 18: Benchmarking** — Execute benchmark suite to measure actual Camera FPS, Inference FPS, Control FPS, and Latency percentiles.
19. **Phase 19: Long-Run Stress Test** — 30-minute continuous execution test monitoring memory, CPU, GPU, thread count, and dropped frames.
20. **Phase 20: Final QA & Verification** — Complete 60-point acceptance criteria checklist.
21. **Phase 21: Documentation & Final Validation Report** — Generate `docs/final-validation-report.md` with empirical measurements.
