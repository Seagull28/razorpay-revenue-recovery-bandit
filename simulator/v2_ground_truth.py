"""
v2_ground_truth.py
Calculates synthetic ground-truth recovery probabilities P(recovery | context, action) for V2.

=============================================================================
SYNTHETIC BENCHMARK PROBABILITY NOTICE:
=============================================================================
All recovery probabilities, base curves, and channel multipliers defined in this module
are artificial benchmark parameters created strictly for synthetic simulation and architectural
evaluation. They do NOT represent real-world Razorpay production recovery rates, live merchant SLA
guarantees, or empirical payment channel conversion statistics.
=============================================================================
"""

from typing import Any, Dict
from bandit_retry_scheduler.core.recovery_action import RecoveryAction
from bandit_retry_scheduler.core.context_utils import (
    to_day_bucket,
    to_failure_bucket,
    to_success_bucket,
)
from bandit_retry_scheduler.simulator.config import (
    BANK_D_DRIFT_DAY,
    BANK_D_DRIFT_PROBABILITIES,
    BASE_RECOVERY_PROBABILITIES,
    CUSTOMER_FAILURE_CYCLE_MODIFIERS,
    CUSTOMER_SUCCESS_MODIFIERS,
    NETWORK_MODIFIERS,
    Bank,
    DelayArm,
    FailureCode,
)


def calculate_v2_recovery_probability(context: Dict[str, Any], action: RecoveryAction) -> float:
    """
    Computes the true synthetic ground-truth recovery probability for a V2 RecoveryAction.

    Parameters:
    -----------
    context: Dict containing transaction features (failure_code, bank, network, source_method, etc.)
    action: RecoveryAction instance to evaluate.

    Returns:
    --------
    float: True underlying recovery probability in [0.0, 1.0].
    """
    if not isinstance(action, RecoveryAction):
        raise TypeError("Action must be a RecoveryAction instance.")

    failure_code = context.get("failure_code", FailureCode.GENERIC_DECLINE.value)
    bank = context.get("bank", Bank.BANK_A.value)
    network = context.get("network", "Mastercard")
    simulated_day = context.get("simulated_day", 1)

    target_method = action.target_method

    # 1. EXPLICIT CARD_EXPIRED SYNTHETIC SEMANTICS
    if failure_code == FailureCode.CARD_EXPIRED.value:
        if target_method == "card":
            # Same-method card retry on expired card strictly yields 0.0% recovery
            return 0.0
        elif target_method == "upi":
            # SYNTHETIC ALTERNATIVE-METHOD BASE PROBABILITY for card_expired -> UPI switch
            base_p = 0.40
        elif target_method == "netbanking":
            # SYNTHETIC ALTERNATIVE-METHOD BASE PROBABILITY for card_expired -> Netbanking switch
            base_p = 0.35
        else:
            base_p = 0.30
        
        # Apply success history modifier and clamp
        success_bucket = to_success_bucket(context.get("customer_prior_success_count", "1-3"))
        success_mult = CUSTOMER_SUCCESS_MODIFIERS.get(success_bucket, 1.0)
        return float(max(0.0, min(1.0, base_p * success_mult)))

    # 2. BASE PROBABILITY LOOKUP FOR OTHER FAILURE CODES
    if target_method == "card":
        # Card target reuses existing V1 ground truth base curves
        delay = action.delay if action.delay in ["1hr", "6hr", "1d", "3d", "7d"] else "1d"
        if bank == Bank.BANK_D.value and failure_code == FailureCode.DO_NOT_HONOR.value and simulated_day >= BANK_D_DRIFT_DAY:
            base_p = BANK_D_DRIFT_PROBABILITIES.get(delay, 0.05)
        else:
            bank_curves = BASE_RECOVERY_PROBABILITIES.get(failure_code, {})
            delay_curves = bank_curves.get(bank, {})
            base_p = delay_curves.get(delay, 0.20)
    elif target_method == "upi":
        # Synthetic UPI target base probabilities
        upi_base_map = {
            FailureCode.INSUFFICIENT_FUNDS.value: 0.45,
            FailureCode.ISSUER_TIMEOUT.value: 0.60,
            FailureCode.DO_NOT_HONOR.value: 0.15,
            FailureCode.GENERIC_DECLINE.value: 0.35,
        }
        base_p = upi_base_map.get(failure_code, 0.35)
    elif target_method == "netbanking":
        # Synthetic Netbanking target base probabilities
        nb_base_map = {
            FailureCode.INSUFFICIENT_FUNDS.value: 0.40,
            FailureCode.ISSUER_TIMEOUT.value: 0.50,
            FailureCode.DO_NOT_HONOR.value: 0.12,
            FailureCode.GENERIC_DECLINE.value: 0.30,
        }
        base_p = nb_base_map.get(failure_code, 0.30)
    else:
        base_p = 0.25

    # 3. CONTEXTUAL MODIFIERS
    network_mult = NETWORK_MODIFIERS.get(network, 1.0)

    success_bucket = to_success_bucket(context.get("customer_prior_success_count", "1-3"))
    success_mult = CUSTOMER_SUCCESS_MODIFIERS.get(success_bucket, 1.0)

    failure_bucket = to_failure_bucket(context.get("customer_prior_failures_this_cycle", "0"))
    failure_mult = CUSTOMER_FAILURE_CYCLE_MODIFIERS.get(failure_bucket, 1.0)

    # Day-of-month / Salary boost for insufficient_funds
    day_bucket = context.get("day_of_month_bucket")
    if not day_bucket and "day_of_month" in context:
        day_bucket = to_day_bucket(context["day_of_month"])
    elif not day_bucket:
        day_bucket = "mid"

    salary_mult = 1.0
    if failure_code == FailureCode.INSUFFICIENT_FUNDS.value and day_bucket == "early":
        salary_mult = 1.25 if bank == Bank.BANK_B.value else 1.10

    # 4. AGGREGATION & CLAMPING
    final_p = base_p * network_mult * success_mult * failure_mult * salary_mult
    return float(max(0.0, min(1.0, final_p)))
