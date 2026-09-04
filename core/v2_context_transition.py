"""
v2_context_transition.py
Pure context transition logic for RecoverFlow V2.

Decouples simulation evaluation from transaction state advancement.
Ensures zero side-effects on input context dictionaries.
"""

from typing import Any, Dict
from bandit_retry_scheduler.core.context_utils import to_day_bucket
from bandit_retry_scheduler.core.recovery_action import RecoveryAction

# Duration in simulated days added per delay window string
DELAY_TO_DAYS_MAP: Dict[str, int] = {
    "1hr": 0,
    "6hr": 0,
    "1d": 1,
    "3d": 3,
    "7d": 7,
    "0": 0,
}


def transition_v2_context(
    context: Dict[str, Any],
    action: RecoveryAction,
    outcome: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Computes the next attempt's context state following execution of a V2 RecoveryAction.

    PURE FUNCTION: Does NOT mutate the input context or outcome dictionaries.

    Parameters:
    -----------
    context: Dict containing current transaction context features.
    action: RecoveryAction instance executed.
    outcome: Dict containing simulation execution results ('success', 'reward', etc.).

    Returns:
    --------
    Dict[str, Any]: Re-bound context dictionary for the subsequent attempt.
    """
    if not isinstance(context, dict):
        raise ValueError("Context must be a dictionary.")
    if not isinstance(action, RecoveryAction):
        raise TypeError("Action must be a RecoveryAction instance.")
    if not isinstance(outcome, dict):
        raise ValueError("Outcome must be a dictionary.")

    # 1. Terminal Success: If retry succeeded, lifecycle completes; return copy of context
    if outcome.get("success") is True:
        return dict(context)

    # 2. Failed Attempt: Advance state for subsequent attempt
    new_ctx = dict(context)

    # Lifecycle attempt counter increment
    current_attempt = int(new_ctx.get("retry_attempt_number", 1))
    new_ctx["retry_attempt_number"] = current_attempt + 1

    # Cycle failure count increment ('0' -> '1' -> '2+')
    current_fail = str(new_ctx.get("customer_prior_failures_this_cycle", "0"))
    if current_fail == "0":
        new_ctx["customer_prior_failures_this_cycle"] = "1"
    else:
        new_ctx["customer_prior_failures_this_cycle"] = "2+"

    # Action-type specific evolution
    if action.action_type == "TIMED_RETRY":
        # Advance simulated time by delay days
        delay_days = DELAY_TO_DAYS_MAP.get(action.delay, 0)
        current_day = int(new_ctx.get("simulated_day", 1))
        next_day = current_day + delay_days
        new_ctx["simulated_day"] = next_day

        # Recalculate day of month and salary bucket
        day_of_month = ((next_day - 1) % 31) + 1
        new_ctx["day_of_month"] = day_of_month
        new_ctx["day_of_month_bucket"] = to_day_bucket(day_of_month)

        # Source payment method remains unchanged for timed retry
        new_ctx["source_method"] = action.source_method

    elif action.action_type == "METHOD_SWITCH":
        # Time does not advance for immediate method switch (delay = 0)
        # Source payment method updates to target_method
        new_ctx["source_method"] = action.target_method

    return new_ctx
