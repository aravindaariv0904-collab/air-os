# AirOS — README

## What is AirOS?

AirOS is a **local-first, low-latency, touchless human-computer interface** for Windows.
Control your laptop cursor, scroll, click, drag, and type using only hand gestures detected by your built-in webcam. No cloud, no account, no hardware required beyond your webcam.

---

## Quick Start

### Prerequisites
- Python 3.11 (in `venv/` — already set up)
- Node.js v18+ 
- Windows 10/11

### Install (first time only)
```bat
setup.bat
```

### Launch AirOS
```bat
start.bat
```

### Development Mode (hot reload)
```bat
start_dev.bat
```

---

## Gestures

| Gesture | Action |
|---------|--------|
| ☝️ Index finger up | Move cursor |
| 🤏 Pinch | Left click |
| 🤏 + Move | Drag |
| ↑ Hand up | Scroll up |
| ↓ Hand down | Scroll down |
| ← Swipe left | Navigate back |
| → Swipe right | Navigate forward |
| 🖐️ Open palm (hold 0.8s) | **Pause AirOS** |
| 👐 Two hands (hold 1.5s) | Keyboard mode |

### Safety
- **Ctrl+Alt+A** — Emergency stop (always works)
- **Open palm** — Pauses gesture control
- System tray — Stop/pause from tray menu

---

## Architecture

```
Camera (DirectShow, 30 FPS)
    ↓
Hand Tracker (MediaPipe Tasks, ~16ms)
    ↓
Landmarks (21 points, normalized)
    ↓
Gesture Detectors (temporal confirmation, no single-frame triggers)
    ↓  
State Machine (10 states)
    ↓
SendInput (ctypes, <1ms)
    ↓
Windows cursor/keyboard events

IPC (WebSocket :7890) → Electron Dashboard (separate process)
```

---

## Performance (measured on RTX 4050 laptop)

| Metric | Measured | Target |
|--------|----------|--------|
| Camera FPS | **28.8 avg** | ≥25 |
| MediaPipe inference | **16ms avg** | <50ms |
| Total pipeline latency | **~50ms** | <100ms |
| Dropped frames | **0** | 0 |

---

## Project Structure

```
air-os/
├── engine/               Python real-time pipeline
│   ├── camera/          DirectShow capture
│   ├── tracking/        MediaPipe integration
│   ├── landmarks/       21-point hand geometry
│   ├── filtering/       One Euro Filter
│   ├── motion/          Velocity/displacement
│   ├── gestures/        Gesture detectors
│   ├── state/           State machine
│   └── calibration/     Interaction region
├── input/               Windows input injection
│   ├── windows/         SendInput ctypes
│   ├── mouse/           Cursor engine
│   └── action_registry  Action vocabulary
├── ipc/                 WebSocket IPC server
├── gestures/            Gesture registry + profiles
├── keyboard/            Virtual keyboard
├── apps/desktop/        Electron dashboard (React/TypeScript)
├── tests/               Unit + integration tests
├── scripts/             Diagnostic tools
├── docs/                Architecture + research
└── assets/models/       MediaPipe hand model
```

---

## Running Tests

```powershell
# Unit tests (no webcam needed, 0.6s)
$env:PYTHONIOENCODING="utf-8"
.\venv\Scripts\python.exe -m pytest tests\unit\test_core.py -v

# Integration tests (no webcam needed)
.\venv\Scripts\python.exe tests\integration\test_integration.py

# Live camera + MediaPipe benchmark
.\venv\Scripts\python.exe scripts\bench_stage2.py

# Live interactive test (opens webcam window)
.\venv\Scripts\python.exe scripts\test_stage2_camera.py
```

---

## Privacy

- All processing is **local** — no data leaves the machine
- No cloud API calls, no telemetry, no account required
- Camera frames are **never saved** to disk
- Gesture recordings stay on-device

---

## Safety Mechanisms (3 independent)

1. **Ctrl+Alt+A** global hotkey → immediate engine stop
2. **Open palm gesture** → pause AirOS (no more cursor movement)
3. **System tray → Stop** → graceful shutdown

---

*AirOS v0.1.0 — Built with MediaPipe, OpenCV, Electron, React*
