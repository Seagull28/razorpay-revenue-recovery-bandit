"""
heuristic.py
Domain-knowledge rule-based heuristic policy for Phase 1 Evaluation Hardening.
Uses ONLY observable context features (failure_code, day_of_month_bucket, attempt_number,
customer_prior_success_count, customer_prior_failures_this_cycle).
Zero ground-truth access, completely deterministic.
"""

from typing import Any, Dict
from bandit_retry_scheduler.policies.base import BasePolicy, PolicyDecision
from bandit_retry_scheduler.simulator.config import DelayArm, FailureCode


class ContextualHeuristicPolicy(BasePolicy):
    """
    Expert domain-knowledge rule-based policy for payment retries:
    - issuer_timeout: Short-lived infrastructure glitch -> Attempt 1: 1hr, Attempt 2+: 6hr.
    - insufficient_funds: Balance depletion -> If salary_cycle or high prior success (4+): 1d; else: 3d.
    - do_not_honor: Risk / fraud check -> Attempt 1: 1d, Attempt 2+: 3d.
    - generic_decline: Gateway / card decline -> Attempt 1: 6hr, Attempt 2: 1d, Attempt 3+: 3d.
    - card_expired: Unrecoverable hard stop handled by BasePolicy eligibility -> Attempt 1: 1hr.
    """

    def __init__(self, max_attempts: int = 4):
        super().__init__(max_attempts=max_attempts)

    def select_arm(self, context: Dict[str, Any], attempt_number: int) -> PolicyDecision:
        if attempt_number < 1:
            raise ValueError(f"attempt_number must be >= 1, got {attempt_number}")

        fc = str(context.get("failure_code", FailureCode.GENERIC_DECLINE.value))
        day_bucket = str(context.get("day_of_month_bucket", "mid"))
        prior_success = str(context.get("customer_prior_success_count", "0"))

        if fc == FailureCode.ISSUER_TIMEOUT.value:
            arm = DelayArm.HOUR_1.value if attempt_number == 1 else DelayArm.HOUR_6.value
        elif fc == FailureCode.INSUFFICIENT_FUNDS.value:
            if day_bucket == "salary_cycle" or prior_success == "4+":
                arm = DelayArm.DAY_1.value
            else:
                arm = DelayArm.DAY_3.value
        elif fc == FailureCode.DO_NOT_HONOR.value:
            arm = DelayArm.DAY_1.value if attempt_number == 1 else DelayArm.DAY_3.value
        elif fc == FailureCode.GENERIC_DECLINE.value:
            if attempt_number == 1:
                arm = DelayArm.HOUR_6.value
            elif attempt_number == 2:
                arm = DelayArm.DAY_1.value
            else:
                arm = DelayArm.DAY_3.value
        elif fc == FailureCode.CARD_EXPIRED.value:
            arm = DelayArm.HOUR_1.value
        else:
            arm = DelayArm.DAY_1.value

        return PolicyDecision(
            arm_chosen=arm,
            expected_value=None,
            metadata={
                "attempt_number": attempt_number,
                "policy": "contextual_heuristic",
                "failure_code": fc,
            },
        )
