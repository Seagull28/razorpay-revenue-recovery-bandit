"""
eligibility.py
Safety gate and eligibility pre-check for the RecoverFlow retry scheduler.
Evaluates hard-stop rules before consulting the bandit policy.
"""

from typing import Any, Dict, Tuple
from bandit_retry_scheduler.policies.base import BasePolicy, FailureCode


class EligibilityGate(BasePolicy):
    """
    Default policy wrapper for evaluating hard-stop eligibility rules.
    Extends BasePolicy to reuse canonical should_stop logic directly.
    """
    def select_arm(self, context: Dict[str, Any], attempt_number: int):
        from bandit_retry_scheduler.policies.base import PolicyDecision
        return PolicyDecision(arm_chosen="NONE")


_DEFAULT_GATE = EligibilityGate()


def check_eligibility(
    transaction: Dict[str, Any],
    attempt_number: int = 1,
    previous_success: bool = False,
    max_attempts: int = 4,
) -> Tuple[bool, str]:
    """
    Pre-check layer that runs BEFORE consulting the bandit policy.
    Replicates the exact semantics of BasePolicy.should_stop():
    - Attempt 1 of card_expired IS eligible (1 attempt permitted).
    - Attempt > 1 of card_expired is INELIGIBLE ('hard_stop_card_expired').
    - Attempt > max_attempts is INELIGIBLE ('max_attempts_reached').
    - Previous success is INELIGIBLE ('payment_recovered').

    Parameters:
    -----------
    transaction: dict containing transaction features (failure_code, etc.)
    attempt_number: 1-indexed attempt number (default: 1)
    previous_success: bool indicating if previous attempt succeeded
    max_attempts: int hard cap (default: 4)

    Returns:
    --------
    (eligible: bool, reason: str)
    """
    gate = EligibilityGate(max_attempts=max_attempts)
    should_stop, reason = gate.should_stop(
        context=transaction,
        attempt_number=attempt_number,
        previous_success=previous_success,
    )
    
    # If should_stop is True, the transaction is INELIGIBLE for retry.
    eligible = not should_stop
    status_reason = "eligible" if eligible else reason
    return eligible, status_reason
