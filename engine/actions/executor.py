"""
AirOS Engine — Action Executor
The ONLY way skills are executed from any modality (voice, hand, UI).
Accepts only registered skills with validated parameters. No shell access.

Execution flow:
  ActionRequest -> validate skill -> validate params -> execute on Windows
                -> verifier checks real state -> ActionResponse
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

from engine.actions.skills import SkillRegistry, SkillResult
from engine.actions.verifier import ActionVerifier

logger = logging.getLogger(__name__)


@dataclass
class ActionResponse:
    ok: bool = False
    skill: str = ""
    message: str = ""
    verified: bool = False
    ambiguous: bool = False
    matches: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)
    risk: str = "LOW"


class ActionExecutor:
    """
    Controlled executor for registered desktop skills.

    deps provides the shared runtime dependencies:
      - context: DesktopContextService
      - input: WindowsInputAdapter
      - screenshot: WindowsScreenshotService
      - volume: VolumeController
    """

    def __init__(self, deps: Dict[str, Any]):
        self._registry = SkillRegistry()
        self._verifier = ActionVerifier()
        self._deps = deps
        self._last_response: Optional[ActionResponse] = None
        self._lock = threading.Lock()

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    @property
    def last_response(self) -> Optional[ActionResponse]:
        return self._last_response

    def validate(self, skill: str, params: Dict[str, Any]) -> Optional[str]:
        """Validate that skill+params are executable. Returns error or None."""
        s = self._registry.get(skill)
        if s is None:
            return f"Unknown skill: {skill}"
        return s.validate_params(params or {})

    def execute(
        self,
        skill: str,
        params: Dict[str, Any],
        verify: bool = True,
    ) -> ActionResponse:
        """Validate, execute, and verify a skill. Never raises."""
        start = time.monotonic()
        with self._lock:
            return self._execute_locked(skill, params or {}, verify, start)

    def _execute_locked(self, skill: str, params: Dict[str, Any], verify: bool, start: float) -> ActionResponse:
        s = self._registry.get(skill)
        if s is None:
            resp = ActionResponse(
                ok=False, skill=skill, message=f"Unknown skill: {skill}"
            )
            self._last_response = resp
            return resp

        error = s.validate_params(params or {})
        if error:
            resp = ActionResponse(
                ok=False, skill=skill, message=f"Invalid parameters: {error}"
            )
            self._last_response = resp
            return resp

        try:
            result = s.execute(params or {}, self._deps)
        except Exception as e:
            logger.error(f"Skill '{skill}' execution raised: {e}")
            result = SkillResult(ok=False, skill=skill, message=f"Execution error: {e}")

        if verify and result.ok and not result.ambiguous:
            result = self._verifier.verify(s, result, params or {}, self._deps)

        resp = ActionResponse(
            ok=result.ok,
            skill=skill,
            message=result.message,
            verified=result.verified,
            ambiguous=result.ambiguous,
            matches=result.matches,
            detail=result.detail,
            risk=s.risk,
        )
        resp.detail["elapsed_ms"] = round((time.monotonic() - start) * 1000, 1)
        self._last_response = resp
        if resp.ok:
            logger.info(f"ACTION OK: {skill} {params} -> {resp.message}")
        else:
            logger.warning(f"ACTION FAILED: {skill} {params} -> {resp.message}")
        return resp

    def list_skills(self) -> list:
        return self._registry.list_skills()
