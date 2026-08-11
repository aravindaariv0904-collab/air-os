# AirOS Architecture

**Date:** 2026-08-11  
**Version:** 1.0  
**Status:** Approved — Implementation in progress

---

## 1. System Overview

AirOS is a local-first, low-latency touchless computing interface for Windows. It consists of:

1. **Python Real-Time Engine** — camera, tracking, gesture recognition, Windows input
2. **Electron Desktop Application** — dashboard UI, settings, gesture studio
3. **IPC Bridge** — WebSocket communication between engine and UI

The real-time engine is completely independent of the UI. The UI receives telemetry only.

---

## 2. Process Architecture

```
┌─────────────────────────────────────────────────────┐
│  Python Engine Process (python 3.11 venv)           │
│                                                     │
│  ┌─────────┐  ┌──────────┐  ┌─────────────────┐    │
│  │ Camera  │→ │ Tracking │→ │ Gesture Engine  │    │
│  │ Thread  │  │ Thread   │  │ (same thread)   │    │
│  └─────────┘  └──────────┘  └────────┬────────┘    │
│                                      │              │
│                              ┌───────▼────────┐     │
│                              │ Windows Input  │     │
│                              │ (SendInput)    │     │
│                              └────────────────┘     │
│                                                     │
│  ┌─────────────────────────┐                        │
│  │ Telemetry + IPC Thread  │ ← Non-blocking         │
│  │ WebSocket Server :7890  │                        │
│  └─────────────────────────┘                        │
└─────────────────────────────────────────────────────┘
           │ WebSocket (localhost:7890)
           ↕ 
┌─────────────────────────────────────────────────────┐
│  Electron Process                                   │
│  ┌─────────────────────────────────────────────┐   │
│  │  React UI (Dashboard / Settings / Studio)   │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## 3. Real-Time Pipeline (Python Engine)

```
WEBCAM
  ↓ cv2.CAP_DSHOW @ 640×480 @ 30fps, buffer=1
FRAME CAPTURE (camera/capture.py)
  ↓ latest-frame strategy — stale frames discarded
HAND TRACKING (tracking/hand_tracker.py)
  ↓ MediaPipe HandLandmarker, LIVE_STREAM mode
LANDMARK PROCESSING (landmarks/processor.py)
  ↓ normalize, extract features, compute angles
MOTION ESTIMATION (motion/estimator.py)
  ↓ velocity, acceleration, direction
TEMPORAL FILTERING (filtering/one_euro.py)
  ↓ One Euro Filter on cursor position
GESTURE RECOGNITION (gestures/recognizer.py)
  ↓ geometric + temporal state machine
GESTURE REGISTRY (gestures/registry/)
  ↓ lookup action for gesture + current app
CONFIDENCE VALIDATION (gestures/validator.py)
  ↓ reject if confidence < threshold
INTERACTION STATE MACHINE (engine/state/)
  ↓ IDLE → POINTER → CLICK → DRAG → etc.
ACTION REGISTRY (input/action_registry.py)
  ↓ resolve gesture → action
WINDOWS INPUT (input/windows/send_input.py)
  ↓ ctypes SendInput
LAPTOP OS
```

**The dashboard is NOT in this path.**  
The telemetry thread snapshots state every 100ms and sends it via WebSocket.

---

## 4. Module Map

```
air-os/
├── engine/
│   ├── __init__.py
│   ├── main.py                    # Entry point, orchestrates all modules
│   ├── camera/
│   │   ├── capture.py             # OpenCV camera capture, latest-frame strategy
│   │   └── diagnostics.py        # Camera info, FPS measurement
│   ├── tracking/
│   │   ├── hand_tracker.py        # MediaPipe HandLandmarker wrapper
│   │   └── tracker_config.py     # Confidence thresholds, model paths
│   ├── landmarks/
│   │   ├── processor.py           # Landmark normalization, feature extraction
│   │   ├── geometry.py            # Angles, distances, orientations
│   │   └── definitions.py        # Landmark index constants
│   ├── motion/
│   │   ├── estimator.py           # Velocity, acceleration, direction
│   │   └── history.py             # Rolling position history buffer
│   ├── filtering/
│   │   ├── one_euro.py            # One Euro Filter implementation
│   │   └── ema.py                 # Exponential moving average
│   ├── gestures/
│   │   ├── recognizer.py          # Core gesture recognition (geometric)
│   │   ├── pinch.py               # Pinch detector with state machine
│   │   ├── scroll.py              # Scroll gesture detector
│   │   ├── swipe.py               # Swipe gesture detector
│   │   └── palm.py                # Open palm + two-hand detector
│   ├── state/
│   │   ├── machine.py             # Interaction state machine
│   │   └── states.py              # State enum definitions
│   ├── calibration/
│   │   ├── calibrator.py          # Guided calibration workflow
│   │   └── profile.py             # Calibration profile store
│   └── telemetry/
│       ├── collector.py           # Metrics collection
│       └── reporter.py            # IPC telemetry sender
│
├── input/
│   ├── action_registry.py         # Maps gesture → action
│   ├── mouse/
│   │   ├── cursor.py              # Cursor engine (normalization + mapping)
│   │   └── mapper.py              # Camera coord → screen coord
│   ├── keyboard/
│   │   └── key_sender.py          # Virtual key press via SendInput
│   └── windows/
│       ├── send_input.py          # SendInput ctypes implementation
│       └── app_detector.py        # Active window / app detection
│
├── gestures/
│   ├── registry/
│   │   ├── system_gestures.json   # Built-in gesture definitions
│   │   └── gesture_store.py       # CRUD for gesture registry
│   ├── system/
│   │   └── system_gestures.py    # System gesture implementations
│   ├── custom/
│   │   ├── recorder.py            # Gesture recording workflow
│   │   ├── template.py            # Feature template creation
│   │   └── matcher.py             # Template matching classifier
│   ├── profiles/
│   │   ├── profile_manager.py    # Profile CRUD
│   │   └── profiles.json         # Stored profiles
│   ├── recognition/
│   │   └── classifier.py         # Unified gesture classifier
│   └── conflicts/
│       └── detector.py            # Conflict detection logic
│
├── keyboard/
│   ├── rendering/
│   │   └── layout.py              # Keyboard layout definition
│   ├── targeting/
│   │   └── key_targeter.py        # Finger → key hit detection
│   ├── air_tap/
│   │   └── tap_detector.py        # Air tap detection + debounce
│   └── calibration/
│       └── kb_calibrator.py       # Keyboard interaction calibration
│
├── ipc/
│   ├── server.py                  # WebSocket server (asyncio)
│   ├── messages.py                # Message schema definitions
│   └── handlers.py                # Control command handlers
│
├── config/
│   ├── settings.py                # Global settings manager
│   └── defaults.json              # Default configuration
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── performance/
│   └── gestures/
│
├── benchmarks/
│   └── pipeline_bench.py         # End-to-end latency benchmark
│
├── docs/
│   ├── research.md
│   ├── architecture.md
│   ├── gesture-system.md
│   ├── performance.md
│   ├── testing.md
│   ├── security.md
│   ├── user-guide.md
│   └── limitations.md
│
├── apps/
│   └── desktop/                   # Electron + React application
│       ├── electron/
│       │   ├── main.js            # Electron main process
│       │   ├── preload.js         # Context bridge
│       │   └── tray.js            # System tray
│       ├── src/
│       │   ├── App.tsx
│       │   ├── components/
│       │   │   ├── Dashboard/
│       │   │   ├── GestureStudio/
│       │   │   ├── Settings/
│       │   │   ├── Calibration/
│       │   │   └── Overlay/
│       │   └── hooks/
│       │       └── useEngine.ts   # WebSocket connection hook
│       └── package.json
│
├── assets/
│   └── models/
│       └── hand_landmarker.task   # MediaPipe model file
│
├── requirements.txt
└── README.md
```

---

## 5. State Machine

```
States:
  IDLE        — No hand detected
  POINTER     — Index finger extended, moving cursor
  CLICK       — Pinch confirmed
  DRAG        — Pinch + sustained movement
  SCROLL      — Vertical hand movement
  NAVIGATION  — Swipe in progress
  TWO_HAND    — Two hands detected
  KEYBOARD    — Virtual keyboard active
  PAUSED      — Open palm held (no OS input generated)
  CALIBRATION — Calibration workflow active
  OFF         — Engine stopped

Transitions (simplified):
  IDLE → POINTER      : index finger detected
  POINTER → CLICK     : pinch confirmed (3+ frames)
  CLICK → DRAG        : movement while pinched
  DRAG → POINTER      : pinch released
  POINTER → SCROLL    : vertical velocity > threshold
  POINTER → NAVIGATION: horizontal displacement > threshold, velocity > threshold
  ANY → PAUSED        : open palm held > 800ms
  PAUSED → POINTER    : open palm released
  ANY → TWO_HAND      : two hands detected > 1s
  TWO_HAND → KEYBOARD : deliberate activation hold > 1.5s
  KEYBOARD → POINTER  : hands lowered / single hand
  ANY → OFF           : Ctrl+Alt+A or dashboard STOP
```

---

## 6. Cursor Engine

```
Camera [0,1] normalized coordinates
  ↓ Interaction region clamp (configurable margins)
  ↓ Dead zone (±0.01 — ignore micro-tremor)
  ↓ Adaptive sensitivity (slow → fine, fast → coarse)
  ↓ One Euro Filter (adaptive cutoff by velocity)
  ↓ Map to screen [0, screen_width] × [0, screen_height]
  ↓ SendInput MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
CURSOR
```

---

## 7. Gesture Confirmation Pattern

```python
# All gestures follow this pattern — NEVER single-frame
class GestureDetector:
    REQUIRED_FRAMES = 4          # Must be confirmed for N consecutive frames
    REQUIRED_DURATION = 0.12     # Or N seconds (whichever is longer)
    CONFIDENCE_THRESHOLD = 0.75  # Reject below this
    
    def update(self, features: Features) -> Optional[GestureEvent]:
        is_detected = self._check_geometric_conditions(features)
        if is_detected:
            self._confirm_frames += 1
        else:
            self._confirm_frames = 0
        
        if self._confirm_frames >= self.REQUIRED_FRAMES:
            confidence = self._compute_confidence(features)
            if confidence >= self.CONFIDENCE_THRESHOLD:
                return GestureEvent(...)
        return None
```

---

## 8. IPC Message Schema

```json
// Engine → UI: Telemetry (every 100ms)
{
  "type": "telemetry",
  "timestamp": 1700000000.0,
  "state": "POINTER",
  "gesture": "INDEX_POINTER",
  "confidence": 0.91,
  "fps": {
    "camera": 30.2,
    "avg": 29.8,
    "min": 27.1,
    "dropped": 3
  },
  "latency": {
    "capture_ms": 8.2,
    "inference_ms": 14.1,
    "landmark_ms": 0.4,
    "filter_ms": 0.1,
    "gesture_ms": 1.2,
    "state_ms": 0.3,
    "input_ms": 0.8,
    "total_ms": 25.1
  },
  "system": {
    "cpu_percent": 12.3,
    "ram_mb": 245.1
  },
  "hands": 1
}

// UI → Engine: Control
{
  "type": "control",
  "command": "start" | "stop" | "pause" | "resume" | "calibrate"
}
```

---

## 9. Safety Mechanisms

Three independent, always-available stop paths:

1. **Keyboard shortcut:** Ctrl+Alt+A → immediate engine stop (registered via pynput global hotkey)
2. **Dashboard:** "TURN OFF AIR OS" button → sends `{"type":"control","command":"stop"}` via WebSocket
3. **Gesture:** Open palm held > 800ms → PAUSED state (camera continues, no OS input)

No custom gesture can override mechanism #1 or #2.

---

## 10. Privacy Architecture

- No network calls from engine (only localhost WebSocket).
- No webcam frames transmitted over IPC (landmarks only).
- No gesture data stored remotely.
- Config stored at: `%APPDATA%/AirOS/config.json`
- Logs stored at: `%APPDATA%/AirOS/logs/`
- No account, no cloud, no telemetry to external services.

---

## 11. Build Stages Tracking

| Stage | Description | Status |
|-------|-------------|--------|
| 0 | Research | ✅ Complete |
| 1 | Architecture | ✅ Complete |
| 2 | Camera + MediaPipe | 🔄 In Progress |
| 3 | Motion engine | ⏳ Pending |
| 4 | Cursor | ⏳ Pending |
| 5 | Pinch/Click/Drag | ⏳ Pending |
| 6 | Scroll | ⏳ Pending |
| 7 | Swipe | ⏳ Pending |
| 8 | State machine | ⏳ Pending |
| 9 | Windows SendInput | ⏳ Pending |
| 10 | Calibration | ⏳ Pending |
| 11 | Gesture Registry | ⏳ Pending |
| 12 | Gesture Studio | ⏳ Pending |
| 13 | App profiles | ⏳ Pending |
| 14 | Virtual keyboard | ⏳ Pending |
| 15 | Dashboard | ⏳ Pending |
| 16 | System tray + overlay | ⏳ Pending |
| 17 | Performance optimization | ⏳ Pending |
| 18 | QA | ⏳ Pending |
| 19 | Packaging | ⏳ Pending |
