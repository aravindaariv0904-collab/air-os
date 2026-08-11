"""
AirOS Integration Test — Tests the full pipeline without GUI.
Verifies: gesture registry → tracker → state machine → IPC server → keyboard.
No webcam required — camera is only object-constructed, not started.

Run standalone:
    python tests/integration/test_integration.py

Run via pytest:
    pytest tests/integration -v
"""
import sys, os, time, logging, threading, io
# Project root — always correct regardless of working directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
# Force UTF-8 to handle emoji/arrows on Windows console
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(level=logging.WARNING)


def run_integration_suite():
    """Run all integration checks. Returns a list of error strings (empty = pass)."""
    print("=== AirOS Integration Test ===")
    print()
    errors = []

    # Test 1: Gesture Registry
    print("1. Gesture Registry...")
    try:
        from gestures.registry.manager import GestureRegistry
        registry = GestureRegistry()
        ok = registry.load()
        gestures = registry.get_all_enabled()
        assert len(gestures) >= 9, f"Expected >=9 gestures, got {len(gestures)}"
        g = registry.get_by_id("pinch_click")
        assert g is not None, "pinch_click not found"
        assert g.action == "left_click"
        print(f"   OK - {len(gestures)} gestures loaded, pinch_click -> {g.action}")
    except Exception as e:
        errors.append(f"Gesture Registry: {e}")
        print(f"   FAIL: {e}")

    # Test 2: Calibration Manager
    print("2. Calibration Manager...")
    try:
        from engine.calibration.calibrator import CalibrationManager, CalibrationProfile
        cal = CalibrationManager()
        profile = cal.profile
        assert isinstance(profile, CalibrationProfile)
        assert 0 < profile.region_left < profile.region_right < 1
        print(f"   OK - Default region: ({profile.region_left:.2f},{profile.region_top:.2f})-({profile.region_right:.2f},{profile.region_bottom:.2f})")
    except Exception as e:
        errors.append(f"Calibration: {e}")
        print(f"   FAIL: {e}")

    # Test 3: Action Registry
    print("3. Action Registry...")
    try:
        from input.windows.send_input import WindowsInputAdapter
        from input.action_registry import ActionRegistry
        adapter = WindowsInputAdapter()
        adapter.disable()  # Safety: don't inject during test
        reg = ActionRegistry(adapter)
        actions = reg.get_all_actions()
        assert len(actions) > 20, f"Expected >20 actions, got {len(actions)}"
        assert reg.is_valid_action("left_click")
        assert reg.is_valid_action("scroll_up")
        assert reg.is_valid_action("navigate_back")
        print(f"   OK - {len(actions)} actions registered")
    except Exception as e:
        errors.append(f"Action Registry: {e}")
        print(f"   FAIL: {e}")

    # Test 4: Virtual Keyboard Layout
    print("4. Virtual Keyboard...")
    try:
        from keyboard.air_tap.tap_detector import VirtualKeyboard, build_keyboard_layout
        kb = VirtualKeyboard()
        layout = build_keyboard_layout()
        assert len(layout) > 30, f"Expected >30 keys, got {len(layout)}"
        labels = [k.label for k in layout]
        assert "Q" in labels and "SPACE" in labels and "ENTER" in labels
        print(f"   OK - {len(layout)} keys in layout")
    except Exception as e:
        errors.append(f"Virtual Keyboard: {e}")
        print(f"   FAIL: {e}")

    # Test 5: IPC Server
    print("5. IPC Server...")
    try:
        from ipc.server import IPCServer
        ipc = IPCServer(port=7891)  # Use different port for test
        ipc.start()
        time.sleep(0.5)
        ipc.push_telemetry({"type": "telemetry", "test": True})
        time.sleep(0.2)
        ipc.stop()
        print("   OK - IPC server started and stopped cleanly")
    except Exception as e:
        errors.append(f"IPC Server: {e}")
        print(f"   FAIL: {e}")

    # Test 6: Camera Init (don't start, just init)
    print("6. Camera Init...")
    try:
        from engine.camera.capture import CameraCapture, CameraConfig
        cam = CameraCapture(CameraConfig(camera_index=0, width=640, height=480, fps=30))
        # Just verify object was created
        assert cam is not None
        print("   OK - CameraCapture object created")
    except Exception as e:
        errors.append(f"Camera Init: {e}")
        print(f"   FAIL: {e}")

    # Test 7: Full State Machine cycle
    print("7. State Machine Cycle...")
    try:
        from engine.state.machine import StateMachine
        from engine.state.states import InteractionState, GestureType
        sm = StateMachine()
        assert sm.state == InteractionState.IDLE

        # IDLE → POINTER
        sm.process(GestureType.INDEX_POINTER, False, False, 1, True, 0.0)
        assert sm.state == InteractionState.POINTER, f"Expected POINTER, got {sm.state}"

        # POINTER → DRAG (pinch)
        sm.process(GestureType.PINCH, True, False, 1, True, 0.0)
        assert sm.state == InteractionState.DRAG, f"Expected DRAG, got {sm.state}"

        # DRAG → POINTER (release)
        sm.process(GestureType.INDEX_POINTER, False, False, 1, True, 0.0)
        assert sm.state == InteractionState.POINTER, f"Expected POINTER after release, got {sm.state}"

        # Any state → PAUSED (open palm)
        sm.process(GestureType.OPEN_PALM, False, False, 1, False, 0.0)
        assert sm.state == InteractionState.PAUSED, f"Expected PAUSED, got {sm.state}"

        print("   OK - IDLE→POINTER→DRAG→POINTER→PAUSED")
    except Exception as e:
        errors.append(f"State Machine: {e}")
        print(f"   FAIL: {e}")

    # Summary
    print()
    print("=== INTEGRATION TEST RESULTS ===")
    total = 7
    passed = total - len(errors)
    print(f"Passed: {passed}/{total}")
    if errors:
        print("FAILED:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("All tests PASSED.")
    return errors


def test_integration_suite():
    """Pytest entry point — runs the full integration suite."""
    errs = run_integration_suite()
    assert not errs, f"Integration failures: {errs}"


if __name__ == "__main__":
    errs = run_integration_suite()
    sys.exit(1 if errs else 0)
