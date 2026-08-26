"""
fixed_schedule.py
Industry-standard fixed-schedule retry policy (1d -> 3d -> 7d).
Serves as the naive, context-blind baseline comparison point for bandit policies.
"""

from typing import Any, Dict, List, Optional
from bandit_retry_scheduler.policies.base import BasePolicy, PolicyDecision
from bandit_retry_scheduler.simulator.config import DelayArm


class FixedSchedulePolicy(BasePolicy):
    """
    Fixed-schedule retry policy adhering to the naive industry standard:
    Attempt 1: 1d
    Attempt 2: 3d
    Attempt 3: 7d
    Attempt 4 (4th attempt behavior): repeats 7d (standard final-retry hold delay)

    This policy is strictly context-blind: it never inspects failure_code,
    bank, network, or customer history to choose delays.
    """

    # Fixed delay sequence across attempts
    SCHEDULE_SEQUENCE: List[str] = [
        DelayArm.DAY_1.value,  # Attempt 1: 1d
        DelayArm.DAY_3.value,  # Attempt 2: 3d
        DelayArm.DAY_7.value,  # Attempt 3: 7d
    ]

    def __init__(self, max_attempts: int = 4):
        super().__init__(max_attempts=max_attempts)

    def select_arm(self, context: Dict[str, Any], attempt_number: int) -> PolicyDecision:
        """
        Selects a retry delay strictly based on attempt_number:
        - Attempt 1 -> 1d
        - Attempt 2 -> 3d
        - Attempt 3 -> 7d
        - Attempt 4 -> 7d (repeats final delay bucket when max_attempts == 4)

        Expected value is None since the fixed baseline does not model value.
        """
        if attempt_number < 1:
            raise ValueError(f"attempt_number must be >= 1, got {attempt_number}")

        # Indexing into the 3-element schedule:
        # attempt 1 -> idx 0 ('1d')
        # attempt 2 -> idx 1 ('3d')
        # attempt 3 -> idx 2 ('7d')
        # attempt 4+ -> repeats idx 2 ('7d')
        idx = min(attempt_number - 1, len(self.SCHEDULE_SEQUENCE) - 1)
        arm_chosen = self.SCHEDULE_SEQUENCE[idx]

        return PolicyDecision(
            arm_chosen=arm_chosen,
            expected_value=None,
            metadata={"attempt_number": attempt_number, "policy": "fixed_schedule"},
        )
