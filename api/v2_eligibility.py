"""
v2_eligibility.py
Contextual Eligibility Gate for RecoverFlow V2.
Evaluates transaction safety rules and filters candidate RecoveryAction objects.
"""

from typing import Any, Dict, Sequence, Tuple
from bandit_retry_scheduler.core.recovery_action import RecoveryAction
from bandit_retry_scheduler.simulator.config import FailureCode


def check_v2_eligibility(
    context: Dict[str, Any],
    candidates: Sequence[RecoveryAction],
    attempt_number: int = 1,
    previous_success: bool = False,
    max_attempts: int = 4,
) -> Tuple[bool, Tuple[RecoveryAction, ...], str]:
    """
    Evaluates universal safety stopping rules and filters candidate RecoveryAction objects.

    Parameters:
    -----------
    context: Dict containing transaction features.
    candidates: Sequence of RecoveryAction objects (retrieved from ActionRegistry).
    attempt_number: int current attempt count (1-indexed).
    previous_success: bool whether a prior retry attempt succeeded.
    max_attempts: int maximum allowed attempts per transaction.

    Returns:
    --------
    Tuple[is_eligible: bool, eligible_candidates: Tuple[RecoveryAction, ...], reason: str]
    """
    if previous_success:
        return False, (), "payment_recovered"

    if attempt_number > max_attempts:
        return False, (), f"max_attempts_reached_{max_attempts}"

    if not candidates:
        return False, (), "no_candidates_provided"

    failure_code = context.get("failure_code")

    eligible_list = []
    for action in candidates:
        if not isinstance(action, RecoveryAction):
            continue

        # Rule for card_expired:
        # Same-method card retries are INELIGIBLE after attempt 1.
        # Alternative method switches (UPI/Netbanking) remain ELIGIBLE.
        if failure_code == FailureCode.CARD_EXPIRED.value and action.target_method == "card" and attempt_number > 1:
            continue

        eligible_list.append(action)

    if not eligible_list:
        return False, (), "hard_stop_card_expired" if failure_code == FailureCode.CARD_EXPIRED.value else "no_eligible_actions"

    return True, tuple(eligible_list), "continue"
