"""
AirOS Engine — Action Verifier
Verifies that a real Windows state change actually occurred after execution.
Verification depends on the skill; some actions (key injection) report
"unverified" honestly rather than pretending success.
"""

import logging
from typing import Optional

from engine.actions.skills import Skill, SkillResult

logger = logging.getLogger(__name__)


class ActionVerifier:
    """Verifies the real desktop state after an action."""

    def verify(
        self,
        skill: Skill,
        result: SkillResult,
        params: dict,
        deps: dict,
    ) -> SkillResult:
        """
        Run the skill's verifier against real system state.
        Returns the result with `verified` set truthfully.
        """
        if not result.ok or result.ambiguous:
            result.verified = False
            return result
        try:
            result.verified = skill.verify(result, params, deps)
        except Exception as e:
            logger.warning(f"Verifier for '{skill.name}' raised: {e}")
            result.verified = False
        if result.verified:
            result.message = f"{result.message} (verified)"
        else:
            result.message = f"{result.message} (unverified)"
        return result
