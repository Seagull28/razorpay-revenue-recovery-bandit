"""
ground_truth.py
Calculates the hidden ground-truth recovery probability P(recover | context, delay).
Includes base probability matrices, contextual modifiers, salary-day effects, and Bank D drift.
"""

from typing import Any, Dict, Union
from bandit_retry_scheduler.simulator.config import (
    BANK_D_DRIFT_DAY,
    BANK_D_DRIFT_PROBABILITIES,
    BASE_RECOVERY_PROBABILITIES,
    CUSTOMER_FAILURE_CYCLE_MODIFIERS,
    CUSTOMER_SUCCESS_MODIFIERS,
    DAY_OF_MONTH_BOUNDARIES,
    NETWORK_MODIFIERS,
    Bank,
    DelayArm,
    FailureCode,
)


from bandit_retry_scheduler.core.context_utils import (
    to_day_bucket,
    to_failure_bucket,
    to_success_bucket,
)


def calculate_recovery_probability(context: Dict[str, Any], delay: str) -> float:
    """
    Computes the true ground-truth recovery probability for a failed payment retry.

    Parameters:
    -----------
    context: Dict containing the 7 context features plus simulation metadata:
        - 'failure_code': str (e.g., 'insufficient_funds', 'issuer_timeout', etc.)
        - 'bank': str (e.g., 'Bank A', 'Bank B', 'Bank C', 'Bank D')
        - 'network': str (e.g., 'Visa', 'Mastercard', 'RuPay')
        - 'retry_attempt_number': int (1-4)
        - 'day_of_month_bucket': str ('early', 'mid', 'late') or 'day_of_month': int (1-31)
        - 'customer_prior_success_count': str ('0', '1-3', '4+') or int
        - 'customer_prior_failures_this_cycle': str ('0', '1', '2+') or int
        - 'simulated_day': int (1-30, optional, defaults to 1; used for Bank D drift)
    delay: str ('1hr', '6hr', '1d', '3d', '7d')

    Returns:
    --------
    float: True underlying probability of recovery in [0.0, 1.0].
    """
    failure_code = context.get("failure_code", FailureCode.GENERIC_DECLINE.value)
    bank = context.get("bank", Bank.BANK_A.value)
    network = context.get("network", "Mastercard")

    # Hard-rule: Card expired never recovers under any circumstances
    if failure_code == FailureCode.CARD_EXPIRED.value:
        return 0.0

    simulated_day = context.get("simulated_day", 1)

    # 1. Base recovery curve lookup (with Bank D drift check)
    if bank == Bank.BANK_D.value and failure_code == FailureCode.DO_NOT_HONOR.value and simulated_day >= BANK_D_DRIFT_DAY:
        base_p = BANK_D_DRIFT_PROBABILITIES.get(delay, 0.05)
    else:
        bank_curves = BASE_RECOVERY_PROBABILITIES.get(failure_code, {})
        delay_curves = bank_curves.get(bank, {})
        base_p = delay_curves.get(delay, 0.20)

    # 2. Network modifier
    network_mult = NETWORK_MODIFIERS.get(network, 1.0)

    # 3. Customer prior success modifier
    success_bucket = to_success_bucket(context.get("customer_prior_success_count", "1-3"))
    success_mult = CUSTOMER_SUCCESS_MODIFIERS.get(success_bucket, 1.0)

    # 4. Customer prior failures in this cycle modifier
    # (Folded cycle fatigue here per user instruction #1; no separate attempt penalty)
    failure_bucket = to_failure_bucket(context.get("customer_prior_failures_this_cycle", "0"))
    failure_mult = CUSTOMER_FAILURE_CYCLE_MODIFIERS.get(failure_bucket, 1.0)

    # 5. Salary-day / Day-of-month modifier (specifically for insufficient_funds)
    day_bucket = context.get("day_of_month_bucket")
    if not day_bucket and "day_of_month" in context:
        day_bucket = to_day_bucket(context["day_of_month"])
    elif not day_bucket:
        day_bucket = "mid"

    salary_mult = 1.0
    if failure_code == FailureCode.INSUFFICIENT_FUNDS.value:
        if day_bucket == "early":
            # Bank B is especially responsive near the 1st of the month
            salary_mult = 1.25 if bank == Bank.BANK_B.value else 1.10
        elif day_bucket == "late" and delay in [DelayArm.DAY_3.value, DelayArm.DAY_7.value]:
            # Retrying with longer delay late in the month pushes execution into the early salary window
            salary_mult = 1.15 if bank == Bank.BANK_B.value else 1.05

    # 6. Final probability aggregation and clamping
    final_p = base_p * network_mult * success_mult * failure_mult * salary_mult
    return float(max(0.0, min(1.0, final_p)))
