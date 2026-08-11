"""
AirOS — Profile Manager
Auto-switches the active gesture profile based on the foreground application.

The registry holds profile definitions with app matchers. The ProfileManager
polls the foreground app (rate-limited) and activates the matching profile,
then notifies the engine so it can re-apply gesture thresholds.
"""

import logging
import time
from typing import Callable, Optional

from gestures.registry.manager import GestureRegistry

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 1.0  # seconds


class ProfileManager:
    """Detects the foreground app and activates the matching gesture profile."""

    def __init__(self, registry: GestureRegistry,
                 foreground_detector=None,
                 poll_interval: float = DEFAULT_POLL_INTERVAL):
        self._registry = registry
        self._foreground = foreground_detector
        self._poll_interval = poll_interval
        self._last_check = 0.0
        self._last_app = ""
        self._profile_changed: Optional[Callable[[str], None]] = None

    def on_profile_changed(self, callback: Callable[[str], None]):
        """Register a callback invoked with the new active profile id."""
        self._profile_changed = callback

    def update(self, now: float | None = None) -> str:
        """Poll the foreground app and switch profiles if needed (rate-limited).

        Returns the active profile id.
        """
        now = now if now is not None else time.monotonic()
        if now - self._last_check < self._poll_interval:
            return self.active_profile_id

        self._last_check = now
        if self._foreground is None:
            return self.active_profile_id

        app = self._foreground.get_foreground_process()
        self._last_app = app

        profile = self._registry.get_profile_for_app(app)
        if profile is None:
            return self.active_profile_id

        if profile.id != self._registry.active_profile.id:
            if self._registry.set_active_profile(profile.id):
                logger.info(f"Profile auto-switched to '{profile.id}' for app '{app}'")
                if self._profile_changed:
                    try:
                        self._profile_changed(profile.id)
                    except Exception as e:
                        logger.error(f"Profile change callback failed: {e}")

        return self.active_profile_id

    @property
    def active_profile_id(self) -> str:
        return self._registry.active_profile.id if self._registry.active_profile else "default"

    @property
    def last_app(self) -> str:
        return self._last_app

    def set_profile(self, profile_id: str) -> bool:
        """Manually activate a profile."""
        if self._registry.set_active_profile(profile_id):
            if self._profile_changed:
                try:
                    self._profile_changed(profile_id)
                except Exception as e:
                    logger.error(f"Profile change callback failed: {e}")
            return True
        return False
