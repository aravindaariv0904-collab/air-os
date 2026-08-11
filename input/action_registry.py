"""
AirOS — Action Registry
Maps gesture IDs and action names to concrete Windows input operations.
This is the controlled action vocabulary — no arbitrary shell commands.
"""

import logging
from typing import Optional, Dict, Any, Callable
from input.windows.send_input import WindowsInputAdapter, VK

logger = logging.getLogger(__name__)


class ActionRegistry:
    """
    Registry of all available gesture actions.
    
    Actions are callable by name string.
    The registry enforces the allowed action vocabulary.
    No arbitrary code execution from gestures.
    """

    def __init__(self, adapter: WindowsInputAdapter):
        self._adapter = adapter
        self._actions: Dict[str, Callable] = {}
        self._execution_count: Dict[str, int] = {}
        self._register_all()

    def _register_all(self):
        """Register all available actions."""
        a = self._adapter

        # ─── Mouse ────────────────────────────────────────────────────
        self._register("left_click", lambda: a.left_click())
        self._register("right_click", lambda: a.right_click())
        self._register("double_click", lambda: a.double_click())
        self._register("mouse_down", lambda: a.mouse_down("left"))
        self._register("mouse_up", lambda: a.mouse_up("left"))

        # ─── Scroll ───────────────────────────────────────────────────
        self._register("scroll_up", lambda: a.scroll_up(3))
        self._register("scroll_up_slow", lambda: a.scroll_up(1))
        self._register("scroll_up_fast", lambda: a.scroll_up(6))
        self._register("scroll_down", lambda: a.scroll_down(3))
        self._register("scroll_down_slow", lambda: a.scroll_down(1))
        self._register("scroll_down_fast", lambda: a.scroll_down(6))

        # ─── Navigation ───────────────────────────────────────────────
        self._register("navigate_back", lambda: a.key_press(VK.BROWSER_BACK))
        self._register("navigate_forward", lambda: a.key_press(VK.BROWSER_FORWARD))
        self._register("navigate_home", lambda: a.key_press(VK.HOME))
        self._register("navigate_end", lambda: a.key_press(VK.END))
        self._register("page_up", lambda: a.key_press(VK.PAGE_UP))
        self._register("page_down", lambda: a.key_press(VK.PAGE_DOWN))

        # ─── Keyboard ─────────────────────────────────────────────────
        self._register("key_backspace", lambda: a.key_press(VK.BACK))
        self._register("key_enter", lambda: a.key_press(VK.RETURN))
        self._register("key_escape", lambda: a.key_press(VK.ESCAPE))
        self._register("key_tab", lambda: a.key_press(VK.TAB))
        self._register("key_space", lambda: a.key_press(VK.SPACE))
        self._register("key_delete", lambda: a.key_press(VK.DELETE))
        self._register("key_up", lambda: a.key_press(VK.UP))
        self._register("key_down", lambda: a.key_press(VK.DOWN))
        self._register("key_left", lambda: a.key_press(VK.LEFT))
        self._register("key_right", lambda: a.key_press(VK.RIGHT))

        # ─── Media ────────────────────────────────────────────────────
        self._register("media_play_pause", lambda: a.key_press(VK.MEDIA_PLAY_PAUSE))
        self._register("media_next", lambda: a.key_press(VK.MEDIA_NEXT_TRACK))
        self._register("media_prev", lambda: a.key_press(VK.MEDIA_PREV_TRACK))
        self._register("media_stop", lambda: a.key_press(VK.MEDIA_STOP))
        self._register("volume_up", lambda: a.key_press(VK.VOLUME_UP))
        self._register("volume_down", lambda: a.key_press(VK.VOLUME_DOWN))
        self._register("volume_mute", lambda: a.key_press(VK.VOLUME_MUTE))

        # ─── Windows ──────────────────────────────────────────────────
        self._register("win_minimize", lambda: a.hotkey(VK.LWIN, VK.char_to_vk('D')))
        self._register("win_maximize", lambda: a.hotkey(VK.LWIN, VK.UP))
        self._register("win_close", lambda: a.hotkey(VK.ALT, VK.F4))
        self._register("win_switch", lambda: a.hotkey(VK.ALT, VK.TAB))
        self._register("win_screenshot", lambda: a.hotkey(VK.LWIN, VK.SHIFT, VK.char_to_vk('S')))
        self._register("win_taskview", lambda: a.hotkey(VK.LWIN, VK.TAB))
        self._register("win_search", lambda: a.key_press(VK.LWIN))

        # ─── AirOS control (handled by engine, not SendInput) ─────────
        self._register("pause", None)        # Handled by engine
        self._register("resume", None)       # Handled by engine
        self._register("enter_keyboard", None)
        self._register("exit_keyboard", None)
        self._register("cursor_move", None)  # Handled by cursor engine
        self._register("drag", None)         # Handled by cursor engine

        logger.info(f"ActionRegistry: {len(self._actions)} actions registered")

    def _register(self, name: str, fn: Optional[Callable]):
        self._actions[name] = fn
        self._execution_count[name] = 0

    def execute(self, action_name: str, **kwargs) -> bool:
        """
        Execute a named action.
        Returns True on success, False if action not found or fails.
        Engine-handled actions (cursor_move, pause, etc.) return True without calling SendInput.
        """
        if action_name not in self._actions:
            logger.warning(f"Unknown action: {action_name}")
            return False

        fn = self._actions[action_name]
        if fn is None:
            # Engine-handled action — just count it
            self._execution_count[action_name] += 1
            return True

        try:
            fn()
            self._execution_count[action_name] += 1
            return True
        except Exception as e:
            logger.error(f"Action '{action_name}' failed: {e}")
            return False

    def is_valid_action(self, action_name: str) -> bool:
        return action_name in self._actions

    def get_all_actions(self) -> list:
        """Return list of all registered action names."""
        return list(self._actions.keys())

    def get_stats(self) -> dict:
        return {k: v for k, v in self._execution_count.items() if v > 0}
