"""
AirOS Engine — Input Safety Manager
Tracks all active mouse buttons, keyboard modifiers, active drag state, and input mode.
Guarantees release of all held physical/virtual input signals on engine stop, pause,
tracking loss, camera loss, keyboard exit, or error.
"""

import logging
import threading
from typing import Set, Optional
from input.windows.send_input import WindowsInputAdapter, VK

logger = logging.getLogger(__name__)


class InputSafetyManager:
    """
    Tracks and manages input safety.
    Guarantees zero stuck mouse buttons or stuck modifier keys.
    """

    def __init__(self, adapter: Optional[WindowsInputAdapter] = None):
        self._adapter = adapter or WindowsInputAdapter()
        self._held_mouse_buttons: Set[str] = set()  # 'left', 'right', 'middle'
        self._held_keys: Set[int] = set()           # Virtual key codes
        self._active_drag: bool = False
        self._active_keyboard: bool = False
        self._lock = threading.Lock()

    def record_mouse_down(self, button: str = "left"):
        with self._lock:
            self._held_mouse_buttons.add(button.lower())
            if button.lower() == "left":
                self._active_drag = True
            logger.debug(f"InputSafetyManager: recorded mouse down '{button}'")

    def record_mouse_up(self, button: str = "left"):
        with self._lock:
            self._held_mouse_buttons.discard(button.lower())
            if button.lower() == "left":
                self._active_drag = False
            logger.debug(f"InputSafetyManager: recorded mouse up '{button}'")

    def record_key_down(self, vk_code: int):
        with self._lock:
            self._held_keys.add(vk_code)
            logger.debug(f"InputSafetyManager: recorded key down 0x{vk_code:02X}")

    def record_key_up(self, vk_code: int):
        with self._lock:
            self._held_keys.discard(vk_code)
            logger.debug(f"InputSafetyManager: recorded key up 0x{vk_code:02X}")

    def set_keyboard_mode(self, active: bool):
        with self._lock:
            self._active_keyboard = active

    @property
    def is_drag_active(self) -> bool:
        with self._lock:
            return self._active_drag

    @property
    def is_keyboard_active(self) -> bool:
        with self._lock:
            return self._active_keyboard

    def release_all_held_input(self, reason: str = "safety_trigger") -> int:
        """
        Release all currently held mouse buttons and keyboard modifiers.
        Safe to call from any thread or state transition.
        Returns the number of release operations executed.
        """
        with self._lock:
            count = 0
            if not self._held_mouse_buttons and not self._held_keys and not self._active_drag:
                return 0

            logger.warning(
                f"InputSafetyManager: releasing all held inputs (reason='{reason}'). "
                f"Buttons={list(self._held_mouse_buttons)}, Keys={list(self._held_keys)}"
            )

            # 1. Release mouse buttons
            for btn in list(self._held_mouse_buttons):
                try:
                    self._adapter.mouse_up(btn)
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to release mouse button '{btn}': {e}")
            self._held_mouse_buttons.clear()
            self._active_drag = False

            # 2. Release keyboard modifiers and keys
            for vk in list(self._held_keys):
                try:
                    self._adapter.key_up(vk)
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to release key 0x{vk:02X}: {e}")
            self._held_keys.clear()

            return count


_global_safety_manager: Optional[InputSafetyManager] = None

def get_safety_manager(adapter: Optional[WindowsInputAdapter] = None) -> InputSafetyManager:
    global _global_safety_manager
    if _global_safety_manager is None:
        _global_safety_manager = InputSafetyManager(adapter=adapter)
    return _global_safety_manager
