"""
AirOS Engine — Lifecycle Manager
Manages explicit engine lifecycle states:
STOPPED, STARTING, READY, RUNNING, PAUSED, STOPPING, ERROR.
Exposes readiness events and state change callbacks for IPC without stdout parsing.
"""

import logging
import threading
from enum import Enum, auto
from typing import Callable, Optional, List

logger = logging.getLogger(__name__)


class EngineState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


class EngineLifecycleManager:
    """
    Manages state transitions and readiness notifications for the AirOS engine.
    """

    def __init__(self):
        self._state = EngineState.STOPPED
        self._error_message: Optional[str] = None
        self._callbacks: List[Callable[[EngineState, Optional[str]], None]] = []
        self._lock = threading.Lock()

    @property
    def state(self) -> EngineState:
        with self._lock:
            return self._state

    @property
    def error_message(self) -> Optional[str]:
        with self._lock:
            return self._error_message

    def add_state_callback(self, callback: Callable[[EngineState, Optional[str]], None]):
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def transition_to(self, new_state: EngineState, error_msg: Optional[str] = None) -> bool:
        with self._lock:
            if self._state == new_state and error_msg == self._error_message:
                return False

            old_state = self._state
            self._state = new_state
            if new_state == EngineState.ERROR:
                self._error_message = error_msg or "Unknown engine error"
            elif new_state != EngineState.ERROR:
                self._error_message = None

            logger.info(f"EngineLifecycle: {old_state.value.upper()} → {new_state.value.upper()}" +
                        (f" (Error: {error_msg})" if error_msg else ""))

            callbacks_to_call = list(self._callbacks)

        # Notify callbacks outside lock to prevent deadlocks
        for cb in callbacks_to_call:
            try:
                cb(new_state, error_msg)
            except Exception as e:
                logger.error(f"Error in engine lifecycle callback: {e}")

        return True

    def is_running(self) -> bool:
        with self._lock:
            return self._state in (EngineState.RUNNING, EngineState.PAUSED)

    def is_ready(self) -> bool:
        with self._lock:
            return self._state == EngineState.READY


_global_lifecycle_manager: Optional[EngineLifecycleManager] = None

def get_lifecycle_manager() -> EngineLifecycleManager:
    global _global_lifecycle_manager
    if _global_lifecycle_manager is None:
        _global_lifecycle_manager = EngineLifecycleManager()
    return _global_lifecycle_manager
