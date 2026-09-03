"""
static_arm.py
Static arm policies for Phase 1 Evaluation Hardening.
Implements:
1. StaticArmPolicy: Always selects a single fixed retry delay arm.
2. BestStaticArmPolicy: Evaluated and frozen on validation seeds prior to benchmark testing.
"""

from typing import Any, Dict, List, Optional
from bandit_retry_scheduler.policies.base import BasePolicy, PolicyDecision
from bandit_retry_scheduler.simulator.config import DELAY_ARMS, DelayArm


class StaticArmPolicy(BasePolicy):
    """
    Fixed single-arm policy that always selects the specified retry arm (e.g. '1hr', '6hr', '1d', '3d', or '7d')
    for every eligible retry attempt, context-blind.
    """

    def __init__(self, target_arm: str, max_attempts: int = 4):
        super().__init__(max_attempts=max_attempts)
        if target_arm not in DELAY_ARMS:
            raise ValueError(f"Invalid target_arm '{target_arm}'. Must be one of {DELAY_ARMS}")
        self.target_arm = target_arm

    def select_arm(self, context: Dict[str, Any], attempt_number: int) -> PolicyDecision:
        if attempt_number < 1:
            raise ValueError(f"attempt_number must be >= 1, got {attempt_number}")

        return PolicyDecision(
            arm_chosen=self.target_arm,
            expected_value=None,
            metadata={"attempt_number": attempt_number, "policy": f"static_{self.target_arm}"},
        )


class BestStaticArmPolicy(BasePolicy):
    """
    Best static arm policy selected and frozen on held-out validation seeds.
    The benchmark evaluation seeds have ZERO influence on target_arm selection.
    """

    def __init__(self, frozen_arm: str, validation_summary: Optional[Dict[str, Any]] = None, max_attempts: int = 4):
        super().__init__(max_attempts=max_attempts)
        if frozen_arm not in DELAY_ARMS:
            raise ValueError(f"Invalid frozen_arm '{frozen_arm}'. Must be one of {DELAY_ARMS}")
        self.frozen_arm = frozen_arm
        self.validation_summary = validation_summary or {}

    def select_arm(self, context: Dict[str, Any], attempt_number: int) -> PolicyDecision:
        if attempt_number < 1:
            raise ValueError(f"attempt_number must be >= 1, got {attempt_number}")

        return PolicyDecision(
            arm_chosen=self.frozen_arm,
            expected_value=None,
            metadata={
                "attempt_number": attempt_number,
                "policy": "best_static_arm",
                "frozen_arm": self.frozen_arm,
            },
        )
