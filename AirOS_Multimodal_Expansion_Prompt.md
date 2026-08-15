# AirOS — Deep Repository Audit + Production Build Prompt + Verification Loop

## 1. Audit scope

Audited repository: `air-os-main`

Ground truth used:
- Uploaded source tree
- Python source files
- Electron/React source
- configuration and packaging files
- tests
- current repository documentation
- static inspection
- Python bytecode compilation
- local pytest run in the audit environment
- current official Electron / MediaPipe documentation where relevant

Important rule:

> Source code, build output, and executable tests are the source of truth. Existing audit documents must not be treated as proof that a feature works.

---

# 2. Executive verdict

AirOS has a good real-time architecture and a substantial amount of actual implementation, but it is **not yet a production-perfect application**.

The repository is best described as:

**advanced engineering prototype / pre-production desktop application**

not:

**finished installable production product**

The strongest parts are:

- clear Python real-time engine separation
- OpenCV camera capture
- MediaPipe Hand Landmarker integration
- temporal gesture detection
- One Euro cursor filtering
- Windows SendInput layer
- gesture registry
- profile manager
- custom gesture recording/matching core
- calibration manager
- virtual keyboard logic
- Electron + React dashboard shell
- safety mechanisms
- test suite
- standalone-engine packaging specification

The largest gaps are:

1. The frontend still contains simulated/fake functionality.
2. Several UI controls are not actually connected to persistent engine configuration.
3. Gesture Studio UI does not call the Python Gesture Studio implementation.
4. Calibration UI is mostly a visual mock around a real backend workflow.
5. The Electron production build does not automatically build the Python engine before packaging.
6. The production IPC architecture is unauthenticated localhost WebSocket.
7. The packaging/install/update path is not proven from the uploaded repository.
8. Existing documentation overstates what has actually been verified.
9. Cross-platform test collection is not clean because Windows-only code is instantiated on non-Windows audit hosts.
10. Performance telemetry is useful, but the existing latency numbers are not a sufficiently rigorous end-to-end measurement model.
11. The engine currently uses two loosely coordinated control planes: direct Electron IPC and raw engine WebSocket browser mode. These need one authoritative command contract.
12. Configuration is fragmented between hard-coded detector attributes, calibration values, UI-only React state, JSON registries, and profile overrides.
13. There is no single typed configuration model and no versioned migration strategy.
14. There is no robust release/installation QA suite proving a clean-machine experience.
15. There is no final acceptance gate that prevents packaging while a feature is still simulated or disconnected.

---

# 3. Test result from the uploaded repository

Python compilation:

```text
python -m compileall -q .
PASS
```

Pytest:

```text
79 passed
2 failed
```

The two failures were:

```text
Action Registry: module 'ctypes' has no attribute 'WinDLL'
```

and

```text
WindowsInputAdapter(): module 'ctypes' has no attribute 'WinDLL'
```

These failures occurred because the audit runtime is not Windows. This means the repository has a **test-environment portability problem**, not proof that the Windows SendInput implementation itself is broken.

The correct engineering fix is:

- Windows-only tests must be marked/skipped on non-Windows hosts.
- Windows integration tests must run on an actual Windows CI runner.
- A real Windows smoke test must instantiate `WindowsInputAdapter`.
- The release gate must require Windows tests to pass.

Do not “fix” this by mocking the Win32 adapter in the production code.

---

# 4. Repository truth vs documentation truth

The repository documentation contains stale claims.

Examples of contradictions:

- `docs/current-audit.md` says a number of features are complete even though the uploaded UI still simulates several of them.
- The same audit document describes files/directories that are not present in the uploaded repository.
- The README reports performance numbers as measured, while the audit document states that benchmark execution was not performed.
- `apps/desktop/package.json` expects a prebuilt `dist/AirOSEngine` but the normal frontend build command does not build it.
- The uploaded repository does include `assets/models/hand_landmarker.task`, so the older audit statement that the model is absent is stale.
- The code has already fixed some bugs listed as unresolved in the old audit, especially the drag-entry state-machine problem and configuration path handling.

Therefore:

> Rewrite project documentation only after the implementation and acceptance tests are updated. Never use stale audit checkboxes as evidence.

---

# 5. Current architecture assessment

## Good architecture

The intended high-level architecture is sound:

```text
Laptop Camera
     |
     v
Camera Capture
     |
     v
Hand Tracking
     |
     v
Landmarks / Geometry
     |
     v
Motion Estimation
     |
     v
Gesture Detection
     |
     v
Gesture Arbitration
     |
     v
Interaction State Machine
     |
     v
Action Registry
     |
     v
Windows Input Adapter
     |
     v
Windows OS
```

The UI should remain outside the real-time path:

```text
Python Engine
      |
      | telemetry / commands
      v
IPC Layer
      |
      v
Electron Main
      |
      v
Preload / Typed API
      |
      v
React UI
```

This separation should be preserved.

---

# 6. Current architecture problems

## 6.1 Real-time pipeline and UI control contract are not centralized

There is currently:

- Electron -> preload -> IPC -> engine command
- browser UI -> direct WebSocket -> engine command
- Electron main -> raw WebSocket -> engine
- engine -> WebSocket telemetry
- renderer -> Electron IPC for some operations

This is too many paths for a production app.

Required design:

```text
Renderer
   |
   v
Typed Renderer API
   |
   v
Electron Main IPC
   |
   v
Engine Client
   |
   v
Single Engine IPC Contract
```

Browser mode should be treated as a development/debug tool, not a second production control plane.

---

# 7. Critical production gap: Gesture Studio UI is fake

Current `GestureStudio.tsx` uses:

```text
setTimeout(...)
```

to simulate recording.

It also creates fake gesture objects in React memory:

```text
Peace Sign
Thumbs Up
```

The real backend already has:

- `GestureStudio.start_recording()`
- `record_frame()`
- `finish_recording()`
- `cancel_recording()`
- persistence
- template matching
- deletion
- rename
- action assignment

But the UI is not connected to those implementations.

This must be completely replaced.

## Required final behavior

```text
UI Start Recording
        |
        v
Electron IPC
        |
        v
Engine command: gesture_start_recording
        |
        v
Python GestureStudio
        |
        v
Real landmark frames captured
        |
        v
Template validation
        |
        v
Persistent gesture store
        |
        v
Telemetry/event update
        |
        v
UI refreshes actual saved gesture list
```

No simulated recordings.

No fake sample count.

No fake quality percentage.

No hard-coded fake gestures.

---

# 8. Critical production gap: Calibration UI is partially simulated

The Python calibration manager is real.

The React calibration page is not actually driven step-by-step by backend calibration state.

The UI currently:
- increments its own step counter
- shows a fixed hand point
- displays a simplified region
- allows manual Next clicks that do not correspond to every backend step
- does not expose the actual calibration instruction/state machine
- does not provide a real camera preview

Required final behavior:

```text
Backend calibration state
        |
        v
Typed telemetry/event
        |
        v
UI exact current step
        |
        v
Real user instruction
        |
        v
Real detection
        |
        v
Automatic step transition
        |
        v
Persisted calibration
```

The UI must never claim that calibration is finished while the engine has not finalized the calibration profile.

---

# 9. Critical production gap: Settings are not connected

`Settings.tsx` currently stores values in React component state only.

Examples:

- sensitivity
- smoothing
- dead zone
- scroll speed
- pinch threshold
- start minimized
- start on boot
- debug overlay

Changing them does not provide a real persistent configuration flow.

Required architecture:

```text
React Setting
    |
    v
Typed settings command
    |
    v
Engine configuration service
    |
    +--> validate/clamp
    |
    +--> persist to %APPDATA%/AirOS/config.json
    |
    +--> apply runtime changes
    |
    v
return effective configuration
    |
    v
UI shows saved/effective state
```

Every setting must have:

- default
- type
- validation range
- persistence
- runtime application
- UI representation
- test
- migration/version support

---

# 10. Configuration architecture must be unified

Current configuration is spread over:

- calibration profile
- detector class attributes
- hard-coded cursor values
- action registry
- profiles JSON
- system gestures JSON
- React state

Create one authoritative configuration domain model.

Recommended structure:

```text
config/
    schema.py
    defaults.py
    store.py
    migrations.py
    models.py
```

Use explicit versioning:

```json
{
  "schema_version": 1,
  "cursor": {},
  "gestures": {},
  "keyboard": {},
  "startup": {},
  "privacy": {},
  "performance": {},
  "profiles": {}
}
```

Use atomic writes:

```text
write temp file
    ->
fsync
    ->
replace
```

Never corrupt the configuration file if AirOS crashes during save.

---

# 11. Critical IPC security issue

Current Python WebSocket server accepts localhost clients without authentication.

The current design means another local process could attempt to send:

```json
{
  "type": "control",
  "command": "..."
}
```

That is not acceptable for a polished desktop product.

## Production recommendation

Preferred Windows design:

```text
Electron Main
   |
   v
Windows Named Pipe
   |
   v
Python Engine
```

Development fallback:

```text
127.0.0.1 WebSocket
+
per-run random authentication token
+
strict command schema
+
origin/handshake validation
+
rate limiting
```

Never bind control IPC to `0.0.0.0`.

Use a single authenticated command protocol.

Do not expose arbitrary IPC methods.

---

# 12. Electron security must be tightened

The current application already has good foundations:

- `contextIsolation: true`
- `nodeIntegration: false`
- contextBridge usage

Those should remain.

Production hardening must add:

- renderer sandboxing
- CSP
- navigation restrictions
- new-window restrictions
- sender validation for IPC
- strict typed argument validation
- no arbitrary IPC channel forwarding
- no arbitrary shell execution
- no remote web content in the main application
- current supported Electron release
- safe handling of external URLs
- production security headers
- application protocol or packaged local content where appropriate

The Electron documentation explicitly recommends context isolation, sandboxing, restrictive CSP, IPC sender validation, current Electron versions, and limiting navigation/new windows.

---

# 13. Electron version modernization

The uploaded app is pinned around Electron 33.

Current Electron releases in July 2026 are substantially newer; the official release page lists Electron 43.x as stable.

Do not blindly jump major versions.

Required approach:

1. Upgrade Electron deliberately.
2. Read migration notes for every relevant major jump.
3. Test preload behavior.
4. Test sandbox behavior.
5. Test tray APIs.
6. Test packaged startup.
7. Test Windows installer.
8. Test camera/engine launch.
9. Freeze exact release versions in the lockfile.

Do not update dependencies merely for appearance.

---

# 14. Vite modernization

The current app uses Vite 5.

Vite 8.1 was released in June 2026.

A modernization pass should evaluate upgrading the frontend toolchain, but only after checking compatibility with:

- React version
- Electron version
- TypeScript
- electron-builder
- Node runtime
- existing build scripts

Do not perform an uncontrolled dependency upgrade.

---

# 15. MediaPipe design assessment

Using MediaPipe Hand Landmarker in `LIVE_STREAM` mode is technically appropriate for camera interaction.

Official MediaPipe documentation confirms:

- live stream mode is asynchronous
- results arrive through a callback
- timestamps must be monotonically increasing
- the system may drop input images to reduce latency

Therefore the application must design around dropped frames instead of assuming one result per input frame.

Current AirOS already performs result de-duplication, which is good.

However, improve the design so that:

```text
frame_id
capture timestamp
submit timestamp
inference completion timestamp
result timestamp
```

are all explicit and used consistently.

The current `timestamp_ms += 1` approach satisfies monotonicity but does not represent real elapsed milliseconds. Use a monotonic millisecond clock anchored at engine start or a documented frame-time clock.

---

# 16. Latency measurement must be redesigned

Current telemetry mixes different meanings of timing.

For production-grade measurement define:

```text
capture
queue_wait
inference
landmark_processing
motion
gesture
arbitration
state
input
total
```

And define:

```text
P50
P90
P95
P99
max
dropped frames
tracker skipped frames
queue depth
```

Also distinguish:

- processing latency
- user-perceived action latency

For a hand-to-cursor system, user-perceived latency matters more than a single pipeline timestamp.

---

# 17. Real-time loop design

Do not let these run in the real-time path:

- filesystem writes
- configuration saves
- long logging operations
- network waits
- UI operations
- blocking process calls
- expensive template matching across hundreds of templates without a budget

The engine should have:

```text
Capture worker
Tracking worker
Real-time interaction loop
Telemetry worker
Persistence worker
```

with bounded queues.

Never allow an unbounded queue to grow.

The real-time path should prefer dropping stale frames to processing old frames.

---

# 18. Gesture arbitration must remain deterministic

Required priority:

```text
1. Emergency stop
2. Hard pause / safety
3. Calibration lock
4. Keyboard mode
5. Drag
6. Click/pinch
7. Scroll
8. Navigation
9. Pointer
10. Custom gesture
```

Use a deterministic arbitration table.

Every pair of potentially overlapping gestures must have:

- priority
- required evidence
- cooldown
- cancellation condition
- confirmation frames
- confidence threshold

---

# 19. Cursor engine requirements

The current cursor engine is much better than the stale audit document suggests.

It already includes:

- interaction region
- dead zone
- One Euro filtering
- sensitivity around center
- virtual desktop origin
- multi-monitor dimensions
- clamping

Production improvements:

### 19.1 Do not use arbitrary fallback screen dimensions silently

Instead:

```text
Windows API success
    |
    +-- yes -> use actual values
    |
    +-- no -> controlled failure / explicit degraded mode
```

Do not silently pretend that a 1920x1080 display exists.

### 19.2 Re-detect display geometry

Display topology can change while AirOS is running.

Support:

- monitor plug/unplug
- resolution change
- scaling/DPI change

### 19.3 DPI awareness

The application must be tested as a DPI-aware Windows desktop application.

Coordinate mapping must be verified on:

- 100%
- 125%
- 150%
- 175%
- mixed-DPI multi-monitor setups

---

# 20. Windows input safety requirements

`SendInput` is the correct Windows API direction.

But production behavior must include:

- guaranteed mouse button release on shutdown
- guaranteed mouse button release on tracking loss
- guaranteed mouse button release on mode switches
- guaranteed keyboard modifier release
- emergency-stop cleanup
- engine-crash cleanup where possible
- no stuck Shift/Ctrl/Alt/Win keys
- no duplicate mouse-down events
- deterministic drag lifecycle

Add explicit:

```text
InputSafetyManager
```

that owns all held input state.

---

# 21. Virtual keyboard is not production-ready yet

The Python logic exists, but the UI overlay required to actually see and interact with the keyboard is absent.

A production implementation needs:

```text
Transparent always-on-top overlay
        |
        +-- keyboard layout
        +-- hovered key
        +-- tap animation
        +-- typed text preview
        +-- shift state
        +-- close/cancel
        +-- calibration overlay
```

The overlay must be a real Electron window or an appropriate native overlay.

It must not steal focus.

The overlay must not interfere with target application input.

The keyboard must support:

- QWERTY
- Shift
- Caps Lock if intended
- Backspace
- Enter
- Space
- hover highlight
- intentional air tap
- cancellation
- escape
- debouncing
- keyboard calibration

The current Python detector should be treated as the interaction engine, not the complete feature.

---

# 22. Gesture Studio production requirements

A proper custom gesture system must use real examples.

Recommended recording model:

```text
record one example
record N examples
quality gate
feature normalization
template generation
validation set
false-positive test
save template
```

Do not say:

```text
quality = 96%
```

unless that number comes from an actual measured validation process.

Recommended fields:

```json
{
  "id": "...",
  "name": "...",
  "action": "...",
  "version": 1,
  "created_at": "...",
  "examples": 10,
  "duration_ms": 850,
  "quality": {
    "mean_distance": 0.12,
    "threshold": 0.25,
    "validation_pass_rate": 0.94
  }
}
```

---

# 23. Custom gesture false-positive defense

Template matching alone is not enough.

Add:

- movement direction consistency
- start/end pose consistency
- minimum duration
- maximum duration
- confidence threshold
- negative examples
- cooldown
- context restrictions
- foreground application restrictions
- explicit activation region where appropriate

A custom gesture must not accidentally:

- close windows
- mute audio
- change media
- minimize applications
- inject repeated actions

---

# 24. Profile system

The backend profile manager is a good direction.

Production requirements:

```text
foreground app
    |
    v
profile selector
    |
    v
effective configuration
    |
    v
runtime detectors
```

Profile resolution must be deterministic.

Recommended precedence:

```text
Safety rules
>
global configuration
>
active application profile
>
temporary session override
```

Never let an application-specific profile override safety settings.

---

# 25. Settings UI requirements

Every setting control must support:

```text
initial load
save
validation
cancel
reset to defaults
dirty state
save confirmation
runtime application
error handling
```

Recommended sections:

### Control
- sensitivity
- cursor speed
- smoothing
- dead zone

### Gesture
- pinch
- scroll
- swipe
- palm pause
- two-hand activation

### Keyboard
- layout
- target size
- tap threshold
- debounce
- activation mode

### Camera
- camera device
- resolution
- FPS
- mirror

### Safety
- pause gesture
- emergency hotkey
- release-all-input behavior

### Startup
- launch at startup
- launch minimized
- auto-start AirOS

### Privacy
- local-only processing
- log retention
- gesture recording retention

---

# 26. Startup design

Current Electron logic launches the engine, but production startup must be explicit.

Correct production flow:

```text
Application starts
      |
      v
Initialize UI
      |
      v
Resolve engine executable
      |
      v
Launch engine
      |
      v
Engine health handshake
      |
      v
Camera initialization
      |
      v
Tracker initialization
      |
      v
READY
      |
      v
Enable controls
```

Do not use parsing of stdout text such as:

```text
"pipeline started"
```

as the primary readiness mechanism.

Create an explicit IPC handshake:

```text
ENGINE_HELLO
ENGINE_READY
ENGINE_ERROR
ENGINE_STOPPING
ENGINE_STOPPED
```

---

# 27. Engine lifecycle

The lifecycle must be a finite state machine:

```text
STOPPED
  |
  v
STARTING
  |
  +--> ERROR
  |
  v
READY
  |
  v
RUNNING
  |
  v
PAUSED
  |
  v
STOPPING
  |
  v
STOPPED
```

Camera and model initialization errors must map to meaningful user-visible errors.

Examples:

- camera unavailable
- permission issue
- model missing
- tracker initialization failure
- IPC failure
- input injection failure
- configuration corruption

---

# 28. Logging

Use structured logging with:

```text
timestamp
level
component
event
correlation_id
```

Avoid flooding the real-time loop with INFO logs every frame.

Keep:

```text
engine.log
errors.log
```

with rotation.

User data should not be logged unnecessarily.

Do not log webcam frames.

Do not log raw landmark streams continuously.

---

# 29. Privacy

The local-first promise should remain true.

Production requirements:

- no external network calls for core interaction
- no frame upload
- no cloud account
- no hidden telemetry
- no webcam frame persistence
- gesture data stays local
- clear data deletion controls

If any model download is supported:

- use explicit first-run installation
- verify file integrity
- provide offline installation
- do not silently download during runtime

For the packaged product, ship the required model whenever licensing permits.

---

# 30. Dependency management

Do not rely on:

```text
pip install latest
npm install latest
```

for reproducible releases.

Use:

- exact Python dependency pins
- lockfile
- documented supported Python version
- exact Node version
- exact frontend dependency lock
- reproducible build command
- build metadata

Verify compatibility after every dependency change.

---

# 31. Packaging pipeline must become one command

Current package configuration assumes a Python engine build exists.

Required pipeline:

```text
clean
  |
  v
install Python dependencies
  |
  v
run Python tests
  |
  v
build PyInstaller engine
  |
  v
run engine smoke tests
  |
  v
install frontend dependencies
  |
  v
run TypeScript checks
  |
  v
run frontend tests
  |
  v
build Vite app
  |
  v
run Electron packaging
  |
  v
install into clean Windows test VM
  |
  v
run smoke tests
  |
  v
generate release artifact
```

The top-level command should be something like:

```text
scripts/release.ps1
```

and it should fail at the first failed gate.

---

# 32. Tests that must exist

## Unit tests

At minimum:

- cursor mapping
- multi-monitor mapping
- dead zone
- One Euro filter
- pinch detector
- scroll detector
- swipe detector
- open-palm pause
- two-hand activation
- state machine
- arbitration
- action registry
- keyboard layout
- air tap
- calibration
- configuration schema
- configuration migration
- profile selection
- gesture recording
- template validation
- IPC message validation

## Integration tests

- engine startup
- engine shutdown
- camera worker
- tracker callback
- gesture -> action
- drag lifecycle
- pause lifecycle
- calibration lifecycle
- keyboard lifecycle
- custom gesture lifecycle
- profile switching
- telemetry
- IPC handshake

## Windows integration tests

Run on Windows:

- `SendInput`
- screen metrics
- cursor positioning
- multi-monitor
- media keys
- foreground application detection
- tray
- packaged engine
- installer
- startup
- uninstaller

---

# 33. Performance tests

Create reproducible benchmarks.

Required measurements:

```text
camera FPS
tracking FPS
input FPS
end-to-end action latency
P50
P95
P99
max
CPU
RAM
GPU if applicable
frame drops
tracking drops
custom gesture matching cost
```

Run:

```text
5 minute
15 minute
30 minute
60 minute
```

stress sessions.

Acceptance must be based on actual results, not estimates.

---

# 34. Reliability testing

Test:

- camera disconnected
- camera reconnect
- camera busy
- monitor disconnected
- display resolution changed
- laptop sleep/wake
- engine crash
- UI crash
- UI restart while engine continues
- engine restart while UI stays open
- repeated start/stop
- repeated pause/resume
- repeated keyboard activation
- rapid pinch/release
- lost tracking during drag
- application switch during gesture
- configuration corruption
- malformed IPC message
- oversized IPC message
- unexpected WebSocket disconnect

---

# 35. UI design requirements

The UI should feel like a real desktop control product.

Dashboard should contain:

```text
AirOS Status
Camera
Tracking
Current Gesture
Current Action
FPS
Latency
CPU
RAM
Active Profile
Foreground Application
Safety Status
```

Every displayed metric must have a real source.

Never display fabricated:

- confidence
- quality score
- FPS
- latency
- active profile
- calibration state

---

# 36. Dashboard data model

Create a typed state model:

```text
EngineConnectionState
EngineRuntimeState
Telemetry
CalibrationState
GestureStudioState
SettingsState
ProfileState
KeyboardOverlayState
```

Do not scatter raw JSON access throughout React components.

Use one API hook/service.

---

# 37. Frontend architecture

Recommended:

```text
src/
  app/
  pages/
  components/
  hooks/
  services/
  state/
  types/
  utils/
```

Create:

```text
engineClient.ts
settingsClient.ts
gestureClient.ts
calibrationClient.ts
profileClient.ts
```

Renderer components should never manually open random WebSockets.

---

# 38. Error handling

Every async command needs:

```text
loading
success
failure
timeout
retry
```

Example:

```text
Start AirOS
  |
  +--> starting
  +--> ready
  +--> error
```

Show actionable error messages.

Bad:

```text
Failed
```

Good:

```text
AirOS engine could not start because no camera is available.
Connect a camera and try again.
```

---

# 39. Safety model

AirOS is computer-control software.

Therefore safety has priority over convenience.

Implement an `InputSafetyManager`.

Rules:

```text
Emergency stop > everything
Hard pause > gestures
Calibration > interaction
Keyboard mode > navigation
Drag > scroll
```

On any abnormal termination:

```text
release mouse
release keyboard modifiers
disable input
stop camera
stop tracker
close IPC
```

---

# 40. “Perfect” acceptance definition

Absolute perfection cannot be guaranteed.

A realistic production standard is:

### Functional

- every advertised feature works end-to-end
- zero simulated UI behavior
- zero disconnected controls

### Reliability

- no critical crash during stress testing
- no stuck input
- clean recovery from camera loss

### Performance

- measured latency
- measured CPU/RAM
- measured FPS
- no unbounded queue growth

### Security

- no unauthenticated control channel
- restricted Electron IPC
- local-only core operation

### Packaging

- clean Windows install
- Python not required on target
- Node not required on target
- model bundled
- configuration persists
- uninstall cleans application correctly

### Documentation

- documentation matches code
- benchmark numbers are real
- no fabricated claims

---

# 41. Recommended target architecture

```text
                         AIR OS
                           |
             ┌─────────────┴─────────────┐
             |                           |
       DESKTOP UI                  REAL-TIME ENGINE
             |                           |
       React + TS                Camera Manager
             |                           |
       Electron Main             Tracking Manager
             |                           |
       Preload API              Landmark Processor
             |                           |
       Engine Client             Motion Engine
             |                           |
             +------ IPC ----------> Gesture Engine
                                     |
                               Arbitration Engine
                                     |
                               State Machine
                                     |
                              Input Safety Manager
                                     |
                               Action Registry
                                     |
                              Windows Input Adapter
                                     |
                                  Windows
```

Persistent data:

```text
%APPDATA%\AirOS\
    config.json
    calibration.json
    gestures/
    profiles/
    logs/
```

Immutable application resources:

```text
Program Files/AirOS/
    AirOS.exe
    resources/
    engine/
        AirOSEngine.exe
        assets/models/hand_landmarker.task
```

---

# 42. Master application-building prompt

Use the following prompt with the coding agent working on the repository.

::: BEGIN MASTER PROMPT :::

You are the principal engineer responsible for turning the existing AirOS repository into a production-grade Windows desktop application.

AirOS is a local-first touchless human-computer interface that uses a laptop webcam to convert hand movement into reliable Windows interaction.

You are NOT allowed to treat existing documentation, TODO lists, audit documents, screenshots, comments, or previous status claims as proof that a feature works.

The repository source code and executable tests are the source of truth.

Your objective is not to create a demo.

Your objective is to make AirOS function as a coherent desktop product where every UI feature, backend feature, configuration setting, gesture, action, IPC message, calibration step, persistence layer, and packaging step is connected end-to-end.

## NON-NEGOTIABLE RULES

1. Never fabricate implementation.
2. Never simulate a production feature with `setTimeout`, hard-coded objects, fake telemetry, fake scores, or placeholder state.
3. Never claim a metric was measured unless a benchmark actually measured it.
4. Never mark a feature complete because the code exists; prove the user-visible path works.
5. Never add arbitrary shell execution or arbitrary code execution to gesture actions.
6. Never allow a custom gesture to bypass safety rules.
7. Never place blocking file/network/UI operations in the real-time interaction loop.
8. Never use an unauthenticated production control IPC channel.
9. Never silently swallow important exceptions.
10. Never weaken safety to make a feature appear to work.
11. Preserve local-first processing.
12. The primary production target is Windows 10/11.
13. The final product must work without Python or Node.js installed on the target machine.
14. All configurable values must have one authoritative source of truth.
15. Every frontend control must map to a real backend operation and persistence path.
16. Every advertised backend capability must have a real UI path or be explicitly classified as internal.
17. No stale documentation may contradict tested behavior.
18. When uncertain, inspect the implementation and test it instead of guessing.

## PHASE 0 — INVENTORY

Before changing anything:

- recursively inspect every source file
- inspect every package manifest
- inspect lockfiles
- inspect JSON configuration
- inspect models/assets
- inspect tests
- inspect build scripts
- inspect packaging specification
- inspect documentation
- inspect logs
- inspect frontend pages and components
- build a dependency graph
- build a runtime call graph
- build a feature-to-file matrix

Produce an internal inventory:

```text
feature
backend entry point
frontend entry point
IPC command
persistence
tests
packaging requirement
current state
```

Do not modify code until the inventory is complete.

## PHASE 1 — TRUTHFUL BASELINE

Run:

- Python compilation
- unit tests
- integration tests
- frontend type checking
- frontend build
- packaging dry run where possible

On Windows run:

- actual Windows unit tests
- actual Windows integration tests
- actual SendInput test
- actual camera test
- actual packaged engine test

Record actual failures.

Do not “fix” tests by weakening assertions.

Separate:
- code defects
- test harness defects
- environment limitations
- missing infrastructure

## PHASE 2 — NORMALIZE ARCHITECTURE

Create clear packages:

```text
engine/
config/
ipc/
input/
gestures/
keyboard/
apps/desktop/
tests/
scripts/
docs/
```

Do not create duplicate implementations.

Create single authoritative services for:

- configuration
- engine lifecycle
- IPC
- input safety
- gesture arbitration
- settings
- calibration
- custom gesture persistence

## PHASE 3 — CONFIGURATION

Create a typed, versioned configuration model.

It must support:

- defaults
- validation
- load
- save
- atomic write
- schema migration
- reset
- runtime update
- persistence

Store user data under:

```text
%APPDATA%\AirOS\
```

No production writes to Program Files.

## PHASE 4 — ENGINE LIFECYCLE

Implement a real lifecycle:

```text
STOPPED
STARTING
READY
RUNNING
PAUSED
STOPPING
ERROR
```

Expose explicit health/readiness events.

Do not rely on stdout substring detection for readiness.

## PHASE 5 — REAL-TIME ENGINE

Maintain:

```text
Camera
-> Tracker
-> Landmarks
-> Motion
-> Filter
-> Gesture Detection
-> Arbitration
-> State Machine
-> Action Safety
-> Windows Input
```

Requirements:

- bounded processing
- stale-frame dropping
- monotonic timestamps
- no blocking I/O
- deterministic state transitions
- reliable cleanup

Measure real timing per stage.

## PHASE 6 — HAND TRACKING

Use the MediaPipe Hand Landmarker live-stream API correctly.

Requirements:

- bundled model in production
- validated model path
- two-hand support
- callback result handling
- frame/result identity tracking
- dropped-frame accounting
- confidence thresholds
- no duplicate result processing

Do not assume one result per submitted frame.

## PHASE 7 — CURSOR

Implement reliable cursor mapping:

- interaction region
- dead zone
- One Euro filtering
- sensitivity
- screen mapping
- multi-monitor virtual origin
- DPI awareness
- display topology changes
- cursor clamping

Test:
- primary-only
- second monitor right
- second monitor left
- second monitor above
- mixed resolutions
- mixed DPI

## PHASE 8 — GESTURES

Implement deterministic gesture detectors:

- index pointer
- pinch
- click
- drag
- scroll up/down
- swipe left/right
- open palm pause
- two-hand keyboard activation

Every gesture must use temporal confirmation and cooldown.

Document:
- thresholds
- confirmation frames
- release logic
- confidence
- cooldown

## PHASE 9 — ARBITRATION

Create one central arbitration policy.

Required priority:

```text
Emergency stop
Safety pause
Calibration
Keyboard
Drag
Pinch/click
Scroll
Swipe
Pointer
Custom
```

Test every important overlap.

## PHASE 10 — INPUT SAFETY

Create an InputSafetyManager that tracks:

- mouse buttons currently held
- keyboard modifiers currently held
- active drag
- active input mode

On:
- stop
- pause
- tracking loss
- camera loss
- crash handling path
- keyboard exit

release all held input.

Never leave stuck mouse buttons or modifier keys.

## PHASE 11 — ACTION REGISTRY

Keep all supported actions in a controlled allowlist.

Never permit:

- arbitrary shell commands
- arbitrary executable launch
- raw scripting through gesture configuration

Validate action IDs before execution.

## PHASE 12 — CUSTOM GESTURE STUDIO

Replace any simulated frontend implementation.

Implement true workflow:

```text
Start recording
-> real landmark capture
-> sample validation
-> quality calculation
-> example storage
-> template generation
-> confidence threshold
-> persistence
-> action mapping
-> UI refresh
```

Support:

- record
- cancel
- validate
- save
- list
- rename
- delete
- action reassignment
- import/export if intentionally supported

The UI must display real data.

## PHASE 13 — CALIBRATION

The UI must reflect the real backend calibration state.

Implement:

- current step
- instruction
- progress
- actual hand detection
- actual region collection
- pinch calibration
- pause calibration if necessary
- cancellation
- completion
- persistence
- reload

Do not let the UI manually advance backend steps.

## PHASE 14 — VIRTUAL KEYBOARD

Complete the feature end-to-end.

Implement:

- always-on-top transparent overlay
- QWERTY keyboard
- hover state
- air tap
- shift
- backspace
- enter
- space
- escape/cancel
- typed text preview
- close control
- calibration
- focus safety

The overlay must not hijack the target application's focus.

## PHASE 15 — APPLICATION PROFILES

Implement deterministic profile resolution:

```text
safety
>
global
>
application profile
>
temporary override
```

Support:
- foreground app detection
- profile switching
- manual selection
- persistence
- safe override handling

## PHASE 16 — IPC

Implement a strict typed contract.

Every message must have:

```text
type
version
request_id
payload
```

Commands must be allowlisted.

Use Windows named pipes for the production desktop control channel where practical.

If localhost WebSocket remains:

- bind only to 127.0.0.1
- use a per-run random token
- require handshake
- validate every command schema
- rate-limit
- reject malformed messages
- reject unexpected origins/clients where applicable

## PHASE 17 — ELECTRON

Harden BrowserWindow:

- context isolation
- sandbox
- node integration disabled
- strict CSP
- navigation restrictions
- new-window restrictions
- sender validation
- narrow contextBridge API
- no arbitrary IPC
- only packaged/local application content

The renderer must never directly open arbitrary engine sockets in production mode.

## PHASE 18 — FRONTEND

Refactor React into:

```text
pages
components
services
hooks
types
state
utils
```

Create a single engine client.

All pages must use real backend state.

Dashboard:
- status
- camera
- tracking
- gesture
- action
- FPS
- latency
- CPU
- memory
- profile
- foreground application
- safety state

Settings:
- real persistence
- reset
- save
- validation
- effective value

Gesture Studio:
- real recording
- real saved templates
- real quality

Calibration:
- real steps
- real progress
- real instructions

## PHASE 19 — ERROR HANDLING

Use explicit error models.

Each command must have:

```text
pending
success
error
timeout
```

Provide actionable UI errors.

Never display success before backend confirmation.

## PHASE 20 — TESTING

Add/repair:

### Unit
- configuration
- mapping
- filters
- detectors
- state machine
- arbitration
- registry
- keyboard
- calibration
- templates

### Integration
- engine lifecycle
- IPC
- telemetry
- gesture->action
- keyboard
- calibration
- profiles
- custom gestures

### Windows
- SendInput
- cursor
- monitor geometry
- DPI
- tray
- packaged engine
- installer
- startup

### Frontend
- command states
- real data
- error states
- empty states
- loading
- settings persistence

## PHASE 21 — PERFORMANCE

Create benchmark scripts.

Measure:

```text
camera FPS
tracker throughput
queue drops
end-to-end latency
P50
P95
P99
CPU
RAM
```

Run 5/15/30/60 minute tests.

Never invent results.

## PHASE 22 — FAILURE INJECTION

Test:

- camera removed
- camera reconnect
- camera busy
- monitor change
- engine crash
- IPC disconnect
- malformed IPC
- configuration corruption
- repeated start/stop
- repeated pause/resume
- lost tracking during drag
- lost tracking during keyboard mode

## PHASE 23 — PACKAGING

Create one reproducible release pipeline:

```text
clean
-> install deps
-> Python tests
-> Windows tests
-> PyInstaller
-> engine smoke
-> frontend type check
-> frontend build
-> Electron package
-> installer smoke test
-> artifact verification
```

The final installer must:

- launch from Start Menu
- launch without Python
- launch without Node
- ship model
- persist AppData
- create tray
- start engine
- stop engine
- recover from engine error
- uninstall cleanly

## PHASE 24 — DOCUMENTATION

Rewrite:

- README
- architecture
- install guide
- user guide
- testing
- performance
- security
- limitations
- release procedure

Remove all stale claims.

Every benchmark number must have:
- date
- machine
- method
- metric

## PHASE 25 — FINAL ACCEPTANCE

Do not declare completion until all of these are true:

- no simulated feature remains
- no fake telemetry remains
- no dead UI control remains
- no undocumented production behavior remains
- unit tests pass
- integration tests pass
- Windows tests pass
- frontend builds
- engine packages
- Electron packages
- installer installs
- clean-machine smoke test passes
- 30-minute stress test passes
- no stuck input
- no critical crash
- config persists
- IPC is protected
- documentation is truthful

At the end produce:

```text
FINAL_RELEASE_REPORT.md
```

with:
- exact commit/build version
- exact test counts
- exact benchmark values
- known limitations
- package path
- installation validation
- remaining risks

Do not write “production ready” unless every release gate is objectively satisfied.

::: END MASTER PROMPT :::


# 43. Autonomous verification / repair loop prompt

Use this prompt after the master build prompt. Run it repeatedly with the coding agent until the repository reaches the acceptance gate.

::: BEGIN LOOP PROMPT :::

You are now in the AirOS verification-and-repair loop.

Your job is NOT to make superficial changes.

Your job is to repeatedly:

```text
INSPECT
-> TEST
-> IDENTIFY ROOT CAUSE
-> FIX
-> RE-TEST
-> INTEGRATE
-> VERIFY
```

until all applicable release gates pass.

## LOOP RULES

1. Never trust a previous completion message.
2. Never trust a TODO list as proof.
3. Never mark a feature complete without a test or direct runtime evidence.
4. Never replace a failing test with a weaker test just to get green.
5. Never fabricate metrics.
6. Never create mocks for real production functionality unless the mock is explicitly part of a unit test.
7. Never fix one layer while leaving the adjacent layer disconnected.
8. Always trace the full path:

```text
UI
-> IPC
-> engine
-> subsystem
-> persistence
-> UI
```

9. After every functional change, inspect dependent code for integration breakage.
10. After every config change, test persistence and reload.
11. After every IPC change, test malformed and unauthorized messages.
12. After every gesture change, test conflicts and safety.
13. After every packaging change, test the packaged executable.
14. Never stop at “it compiles”.
15. Never stop at “unit tests pass”.
16. Never stop at “UI looks correct”.

## STEP 1 — RE-SCAN

Re-scan the whole repository.

Look specifically for:

```text
setTimeout(
fake telemetry
hard-coded sample data
placeholder
TODO
FIXME
mock
stub
simulation
console-only implementation
unused command
unused API
dead component
unconnected setting
unhandled event
```

Remove production simulation.

## STEP 2 — FEATURE CONTRACT AUDIT

Build this matrix:

```text
Feature
UI
IPC
Backend
Persistence
Runtime behavior
Tests
Packaged behavior
Status
```

Every advertised feature must have all required links.

## STEP 3 — RUN TESTS

Run:

```text
Python compile
pytest
frontend typecheck
frontend build
```

On Windows:

```text
Windows unit/integration
SendInput smoke
camera smoke
package smoke
installer smoke
```

Capture exact failures.

## STEP 4 — CLASSIFY FAILURES

Classify every failure:

```text
A = production defect
B = integration defect
C = test defect
D = environment limitation
E = documentation defect
F = packaging defect
```

Fix A/B/F first.

Repair C without weakening behavior.

Document D.

Repair E after implementation is correct.

## STEP 5 — ROOT-CAUSE FIRST

For each defect:

1. reproduce
2. identify root cause
3. write a minimal regression test
4. fix implementation
5. run focused test
6. run complete test suite
7. inspect neighboring code

Do not patch symptoms only.

## STEP 6 — REAL-TIME SAFETY AUDIT

Check:

- mouse release
- modifier release
- stop behavior
- pause behavior
- camera loss
- tracker loss
- engine crash path
- drag interruption
- keyboard interruption

There must be no path that leaves held input active.

## STEP 7 — IPC AUDIT

Check:

- authentication
- schema validation
- request IDs
- error responses
- timeouts
- connection cleanup
- reconnect
- duplicate commands
- malformed messages
- oversize messages
- unexpected command IDs

Reject anything outside the contract.

## STEP 8 — UI/BACKEND CONSISTENCY AUDIT

For every React control ask:

```text
What exact backend command does this call?
What exact state changes?
Where is it persisted?
What confirms success?
What happens on failure?
Does the UI show the effective value?
```

If any answer is missing, implement it.

## STEP 9 — CONFIGURATION AUDIT

For every configurable parameter:

```text
default
schema
validation
storage
runtime application
reload
reset
migration
test
```

No orphan values.

## STEP 10 — GESTURE QUALITY AUDIT

For each gesture verify:

```text
activation
confirmation
release
cooldown
priority
false positive defense
pause interaction
keyboard interaction
drag interaction
custom gesture interaction
```

## STEP 11 — PERFORMANCE AUDIT

Measure actual:

```text
P50
P95
P99
max latency
FPS
drops
CPU
RAM
```

Repeat the benchmark after optimization.

Never copy old numbers.

## STEP 12 — STRESS LOOP

Run progressively:

```text
5 minutes
15 minutes
30 minutes
60 minutes
```

Check:

- memory
- CPU
- FPS
- latency
- errors
- stuck inputs
- IPC disconnects
- UI responsiveness

## STEP 13 — PACKAGE LOOP

Build the complete application.

Then test the installed artifact.

Do not only run the source version.

Verify:

```text
install
launch
engine start
camera
gesture
cursor
click
drag
scroll
pause
resume
keyboard
custom gesture
settings
calibration
tray
shutdown
uninstall
```

## STEP 14 — CLEAN MACHINE

Test on a Windows machine/VM without:

- Python
- Node.js
- development files
- repository source
- developer environment variables

The installed application must still work.

## STEP 15 — DOCUMENTATION TRUTH AUDIT

Every document must match:

- actual source tree
- actual build process
- actual test count
- actual benchmark values
- actual feature behavior

Delete stale claims.

## STEP 16 — LOOP TERMINATION

Repeat the loop until:

```text
all critical defects = 0
all release blockers = 0
all advertised features = real
all release tests = pass
packaging = pass
clean-machine smoke = pass
stress test = pass
documentation = truthful
```

Only then produce the final release report.

If the loop cannot reach a gate because the required hardware or environment is unavailable:

- do not fabricate a pass
- mark the gate BLOCKED
- explain exactly what environment is required
- still complete every possible local validation

::: END LOOP PROMPT :::


# 44. Priority order for this repository

Implement in this order.

## P0 — Must fix before considering production

1. Remove fake Gesture Studio UI behavior.
2. Connect real Gesture Studio IPC and persistence.
3. Make calibration UI authoritative from backend state.
4. Make Settings fully persistent and runtime-connected.
5. Create unified typed configuration.
6. Make production IPC authenticated/secure.
7. Create explicit engine readiness handshake.
8. Make packaging build the Python engine before Electron packaging.
9. Complete virtual keyboard overlay.
10. Add Windows input safety manager.
11. Add clean Windows release tests.
12. Remove/document stale audit claims.

## P1 — Production hardening

13. DPI-aware multi-monitor validation.
14. Camera loss/reconnect handling.
15. display topology changes.
16. configuration migration.
17. structured logs + rotation.
18. telemetry redesign.
19. negative tests for gesture conflicts.
20. custom gesture validation pipeline.
21. profile precedence rules.
22. error/recovery UX.

## P2 — Quality/performance

23. latency benchmark suite.
24. memory stability tests.
25. long-duration stress testing.
26. UI test suite.
27. packaged-app test suite.
28. release automation.
29. clean machine test.
30. documentation rewrite.

---

# 45. Definition of a truly finished AirOS

The final AirOS should have this chain:

```text
USER
 |
 v
HAND
 |
 v
WEBCAM
 |
 v
CAMERA MANAGER
 |
 v
MEDIAPIPE
 |
 v
LANDMARKS
 |
 v
FILTERING + MOTION
 |
 v
GESTURE DETECTION
 |
 v
ARBITRATION
 |
 v
STATE MACHINE
 |
 v
INPUT SAFETY
 |
 v
ACTION REGISTRY
 |
 v
WINDOWS INPUT
 |
 v
ACTUAL WINDOWS ACTION
```

And the management chain:

```text
USER
 |
 v
REACT UI
 |
 v
TYPED API
 |
 v
ELECTRON MAIN
 |
 v
SECURE IPC
 |
 v
PYTHON ENGINE
 |
 +--> configuration
 +--> calibration
 +--> gesture studio
 +--> profiles
 +--> telemetry
```

And the persistence chain:

```text
UI
 |
 v
Engine
 |
 v
Validated Configuration
 |
 v
Atomic Persistence
 |
 v
%APPDATA%\AirOS
 |
 v
Reload
 |
 v
Effective Runtime State
 |
 v
UI
```

That is the standard the build loop should enforce.

---

# 46. Important technical references

The current official MediaPipe Python API confirms that Hand Landmarker supports LIVE_STREAM mode, uses asynchronous result callbacks, requires monotonically increasing timestamps, and may drop input images to reduce latency.

Electron's current security documentation recommends context isolation, process sandboxing, restrictive CSP, IPC sender validation, limiting navigation and new windows, and keeping Electron current.

Electron stable releases in July 2026 are in the 43.x line.

Vite 8.1 was released in June 2026.

Use these as references when modernizing the stack, but do not blindly upgrade dependencies without compatibility testing.

# 47. Major product expansion — AirOS Multimodal Assistant

AirOS should evolve from a hand-only controller into a multimodal desktop assistant using:

HAND + EYES + VOICE

All three modalities must share one common intent, context, safety, action, verification, and response architecture.

```text
HAND ───────┐
            │
EYE ────────┼──> MULTIMODAL INPUT FUSION
            │             |
VOICE ──────┘             v
                   INTENT ENGINE
                         |
                         v
                   SAFETY POLICY
                         |
                         v
                    ACTION PLAN
                         |
                         v
                  WINDOWS / APPS
```

Do not build three independent command systems.

## 47.1 Eye / face control

Add a face/eye perception subsystem using the webcam.

```text
Webcam
  |
  +--> Hand Landmarker
  |
  +--> Face Landmarker
          |
          +--> eye state
          +--> blink state
          +--> gaze direction
          +--> face presence
```

MediaPipe exposes eye-related blendshapes including `EYE_BLINK_LEFT` and `EYE_BLINK_RIGHT`, which can be used in a blink detector. citeturn508269search4

### Triple-blink screenshot

Required interaction:

```text
blink
blink
blink
```

within a configurable time window.

Pipeline:

```text
3 intentional blinks
        |
        v
Blink Sequence Detector
        |
        v
Confidence + timing validation
        |
        v
SCREENSHOT intent
        |
        v
Screenshot Service
        |
        v
%Pictures%\\AirOS\\Screenshots\\
```

Use a temporal state machine:

```text
IDLE
  |
  v
BLINK_1
  |
  v
BLINK_2
  |
  v
BLINK_3
  |
  v
TRIPLE_BLINK_CONFIRMED
  |
  v
SCREENSHOT
  |
  v
COOLDOWN
  |
  v
IDLE
```

Use minimum eye-closed/open duration, inter-blink timing, sequence timeout, confidence threshold, refractory period, and face tracking confidence. Never count every eyelid closure as a command.

Future eye actions may be configurable:

```text
double blink -> select/confirm
triple blink -> screenshot
long blink   -> pause AirOS
look left    -> previous
look right   -> next
look up      -> scroll up
look down    -> scroll down
```

Do not enable all of them by default.

## 47.2 Screenshot subsystem

Create a real screenshot service supporting:

```text
capture full screen
capture active monitor
capture active window
```

Default triple-blink action:

```text
active-screen screenshot
```

Use an appropriate Windows capture mechanism. Windows Graphics Capture supports display/window capture and frame acquisition for screenshots and other capture scenarios. citeturn508269search5turn508269search15

Required:

- timestamped filenames
- collision-safe names
- PNG by default
- configurable directory
- notification
- failure handling
- no accidental duplicate capture

Default location:

```text
%USERPROFILE%\\Pictures\\AirOS\\Screenshots\\
```

unless changed by the user.

## 47.3 Voice assistant

Add a local-first voice assistant activated by:

```text
Wake word: "Jarvis"
```

Example:

```text
User:
"Jarvis, close the Claude tab."

AirOS:
wake word detected
      |
      v
capture command
      |
      v
speech recognition
      |
      v
intent extraction
      |
      v
desktop context
      |
      v
target resolution
      |
      v
safety validation
      |
      v
action execution
      |
      v
verification
      |
      v
response
```

Another required example:

```text
"Jarvis, open the settings."
```

must open the real Windows Settings application.

## 47.4 Voice architecture

Use:

```text
WakeWordDetector
        |
        v
VoiceActivityDetector
        |
        v
SpeechRecognizer
        |
        v
CommandParser
        |
        v
IntentPlanner
        |
        v
DesktopContext
        |
        v
SafetyPolicy
        |
        v
ActionExecutor
        |
        v
Verifier
        |
        v
ResponseManager
```

The microphone must not continuously upload raw audio.

Default behavior:

```text
low-power wake-word detection
        |
        v
wake word
        |
        v
short command capture
        |
        v
stop capture
```

Create a `SpeechRecognizer` abstraction with local implementations such as `LocalWhisperRecognizer` and `WindowsRecognizer`. Whisper is a general-purpose multilingual speech recognition model and supports transcription and language identification. citeturn508269search14

## 47.5 Wake word

Do not run the full speech-to-text model continuously just to detect "Jarvis".

Create a dedicated `WakeWordDetector` with:
- low CPU use
- false-positive measurement
- false-negative measurement
- configurable wake word
- cooldown
- microphone selection

States:

```text
DISABLED
LISTENING
WAKE_DETECTED
CAPTURING_COMMAND
PROCESSING
SPEAKING
COOLDOWN
ERROR
```

## 47.6 Structured voice intents

Natural language must never be executed directly.

Example:

```json
{
  "intent": "browser.close_tab",
  "target": {
    "application": "Claude",
    "tab_title": "Claude"
  },
  "confidence": 0.92,
  "risk": "medium"
}
```

Then:

```text
intent
   |
   v
target resolver
   |
   v
safety validator
   |
   v
action executor
```

## 47.7 "Jarvis close the Claude tab"

The command must operate on the actual desktop state. Do not use fixed screen coordinates as the main approach.

Prefer:

```text
UI Automation
>
browser/application semantic integration
>
keyboard shortcut after target verification
>
visual fallback only when necessary
```

Microsoft UI Automation exposes a structured desktop/UI tree and control patterns that allow client applications to retrieve and manipulate UI elements. citeturn508269search0turn508269search1turn508269search3

Create adapters where useful:

```text
BrowserAdapter
ClaudeAdapter
VSCodeAdapter
WindowsSettingsAdapter
```

## 47.8 Desktop context

Create `DesktopContext` containing:

```text
active window
process name
application name
window title
monitor
visible UI elements where available
browser/tab state where available
cursor position
```

Refresh context when a voice command begins, foreground application changes, or a contextual command is issued. Prefer semantic UI Automation before OCR or coordinates.

## 47.9 Natural assistant behavior

Example:

```text
User:
"Jarvis, open the settings."

AirOS:
opens Windows Settings
responds:
"Opening Settings."
```

For:

```text
User:
"Jarvis, close the Claude tab."
```

AirOS should recognize, inspect desktop state, identify the correct tab, close it, verify it disappeared, and respond.

If multiple targets match:

```text
"Which Claude tab should I close?"
```

Do not guess.

## 47.10 Command examples

Support:

```text
Jarvis, open Settings.
Jarvis, close the Claude tab.
Jarvis, open Chrome.
Jarvis, switch to VS Code.
Jarvis, minimize this window.
Jarvis, maximize this window.
Jarvis, take a screenshot.
Jarvis, mute the volume.
Jarvis, increase the volume.
Jarvis, scroll down.
Jarvis, search for ...
```

Ambiguous or destructive actions require stronger confirmation.

## 47.11 Risk classification

Create:

```text
LOW
MEDIUM
HIGH
CRITICAL
```

LOW: open app, volume, scroll, screenshot, navigation.

MEDIUM: close tab, switch app, close window, ordinary settings changes.

HIGH: delete data, uninstall, shutdown/restart, important external communication, security changes.

CRITICAL: never execute from an ambiguous command.

The risk policy must be enforced centrally.

## 47.12 Multimodal intent fusion

All modalities use one shared intent model.

Hand:

```json
{"source":"hand","intent":"mouse.click","confidence":0.98}
```

Eye:

```json
{"source":"eye","intent":"screenshot","confidence":0.91}
```

Voice:

```json
{"source":"voice","intent":"browser.close_tab","target":"Claude","confidence":0.94}
```

The Intent Engine consumes all three.

## 47.13 Cross-modal commands

Design for commands such as:

```text
"Jarvis, click that." + index-finger target
look at a window + "Jarvis, close this."
```

Voice supplies the semantic action; hand/eye/desktop context can supply the target.

## 47.14 Attention context

Create `AttentionContext` containing:

```text
voice_command
hand_target
eye_target
active_window
foreground_application
screen_geometry
cursor_position
```

## 47.15 AI planner boundary

Do not put an LLM in every action. Use deterministic routing first. Use an AI planner only for genuine natural-language or contextual reasoning.

The planner must output structured action plans such as:

```json
{
  "actions":[
    {
      "type":"browser.close_tab",
      "target":{"application":"Claude"}
    }
  ],
  "confidence":0.91,
  "requires_confirmation":false
}
```

The Action Executor must reject plans disallowed by the safety policy. The planner/LLM must never directly call Windows APIs.

## 47.16 Response manager

Support:

```text
visual
voice
silent
```

Create `ResponseManager` with asynchronous TTS implementations. Voice output must never block the real-time gesture loop.

## 47.17 Security

Defend against TV/YouTube audio, other speakers, replayed recordings, false wake words, and malicious text displayed on screen.

Important rule:

> Perception is not authorization.

Separate perception, authorization, and execution. A wake word is activation, not identity verification. Sensitive actions should use explicit confirmation or another trusted factor.

## 47.18 Project structure

Recommended:

```text
engine/
  modalities/
    hand/
    eye/
    voice/
  assistant/
    context.py
    intent.py
    planner.py
    safety.py
    executor.py
    response.py
  automation/
    windows.py
    ui_automation.py
    browser.py
    screenshot.py
```

And a skill layer:

```text
skills/
    open_app
    close_window
    close_browser_tab
    switch_app
    screenshot
    volume
    media
    system_settings
    browser_navigation
    text_input
```

Every skill defines name, description, schema, risk, resolver, executor, and verifier.

## 47.19 UI

Add a multimodal dashboard showing real subsystem state:

```text
MULTIMODAL STATUS

Hand
● Active
Gesture: Pointer

Eyes
● Active
State: Open
Blink detector: Ready

Voice
● Listening for "Jarvis"
Microphone: Default
Last command:
"close the Claude tab"

Intent
browser.close_tab
Target: Claude
Confidence: 94%

Action
Executed
```

No fake values.

## 47.20 New settings

### Voice
- enable/disable
- wake word
- microphone
- speech engine
- command timeout
- language
- confidence threshold
- voice responses
- confirmation policy

### Eyes
- enable/disable
- blink sensitivity
- triple-blink window
- eye confidence
- cooldown
- gaze controls

### Multimodal
- modality priority
- combined-input mode
- ambiguity handling
- response mode

## 47.21 Multimodal command lifecycle

Implement:

```text
INPUT
 |
 +--> Hand
 +--> Eye
 +--> Voice
 |
 v
PERCEPTION
 |
 v
NORMALIZATION
 |
 v
INTENT EXTRACTION
 |
 v
DESKTOP CONTEXT
 |
 v
TARGET RESOLUTION
 |
 v
CONFIDENCE
 |
 v
RISK CLASSIFICATION
 |
 v
SAFETY POLICY
 |
 +--> confirmation required
 |
 +--> execute
 |
 v
ACTION PLAN
 |
 v
ACTION EXECUTOR
 |
 v
VERIFICATION
 |
 v
RESPONSE
 |
 v
TELEMETRY
```

Important actions must be verified after execution. For example, for closing a tab, verify that the target tab actually disappeared before reporting success.

## 47.22 Required additions to the master build prompt

The coding agent must treat multimodal support as first-class architecture, not disconnected extras.

### Eye acceptance

```text
intentional blink
intentional blink
intentional blink
```

inside the configured sequence window must produce exactly one screenshot. Normal random blinking must not repeatedly trigger screenshots.

### Voice acceptance

```text
Jarvis, open Settings.
```

must detect wake word, capture speech, create an intent, open Windows Settings, verify success, and generate the configured response.

### Browser acceptance

```text
Jarvis, close the Claude tab.
```

must resolve the real desktop/browser target, close the correct Claude tab, verify closure, and respond.

### Ambiguity acceptance

```text
Jarvis, close that.
```

when no unique target exists must not guess. It should request clarification.

### Multimodal acceptance

```text
Jarvis, click that.
```

while the index finger points at a target must use voice for action and hand for target, produce one action, and verify it.

### Security acceptance

Prove that background audio does not easily execute commands, arbitrary screen text cannot issue commands, wake word alone does not authorize critical actions, malformed intents cannot bypass safety, and planner/LLM output cannot directly invoke OS APIs.

### Performance acceptance

Measure actual wake-word latency, speech recognition latency, intent latency, target resolution latency, action latency, verification latency, total voice-command latency, blink detection latency, triple-blink precision, and eye false-positive/false-negative rates. Never invent benchmark values.

## 47.23 Multimodal release gates

### Eyes
- face tracking works
- blink detection works
- triple-blink state machine works
- false positives are measured
- exactly one screenshot per accepted sequence
- screenshot output is verified
- eye controls can be disabled

### Voice
- wake word works
- false wake rate is measured
- command capture works
- speech recognition works
- structured intent parsing works
- desktop context works
- target resolution works
- safety policy works
- executor works
- verification works
- TTS works if enabled
- microphone can be disabled immediately

### Automation
- Settings opens
- apps open
- application switching works
- supported browser target resolution works
- Claude tab targeting works where the browser exposes suitable semantics
- close action is verified
- ambiguous commands request clarification

### Multimodal
- hand, eye, and voice use one intent system
- duplicate actions are prevented
- modality conflicts have deterministic arbitration
- safety overrides convenience
- telemetry records modality source

### Privacy
- no raw audio upload by default
- camera processing remains local
- no raw audio retention unless explicitly enabled
- every modality can be disabled by the user
