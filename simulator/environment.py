"""
environment.py
Execution environment for the synthetic payment retry simulator.
Exposes simulate_retry(context, delay) -> (success, amount_recovered)
and the RetrySimulator class.
"""

from typing import Any, Dict, Optional, Tuple
import numpy as np

from bandit_retry_scheduler.simulator.config import (
    AMOUNT_DISTRIBUTION_MAPPING,
    AMOUNT_DISTRIBUTION_PARAMS,
    DEFAULT_RETRY_COST,
    DELAY_ARMS,
    FailureCode,
)
from bandit_retry_scheduler.simulator.ground_truth import calculate_recovery_probability


class RetrySimulator:
    """
    Simulates payment retries based on hidden ground-truth probability distributions,
    contextual features, and log-normal transaction amount sampling.
    """

    def __init__(self, seed: Optional[int] = None):
        self.rng = np.random.default_rng(seed)

    def set_seed(self, seed: int) -> None:
        """Resets the random number generator with a specific seed."""
        self.rng = np.random.default_rng(seed)

    def sample_amount(self, failure_code: str) -> float:
        """
        Samples a transaction amount from a log-normal distribution,
        conditioned on the failure code per Section 4.8 & User Instruction #2.
        """
        dist_type = AMOUNT_DISTRIBUTION_MAPPING.get(failure_code, "standard")
        params = AMOUNT_DISTRIBUTION_PARAMS[dist_type]

        raw_amount = self.rng.lognormal(mean=params["mu"], sigma=params["sigma"])
        clipped_amount = max(params["min_amount"], min(params["max_amount"], raw_amount))
        return round(float(clipped_amount), 2)

    def get_true_recovery_probability(self, context: Dict[str, Any], delay: str) -> float:
        """
        Returns the true recovery probability P(recover | context, delay).
        Useful for testing, inspection, and oracle regret calculation in evaluation.
        """
        return calculate_recovery_probability(context, delay)

    def simulate_retry(
        self, context: Dict[str, Any], delay: str
    ) -> Tuple[bool, float]:
        """
        Simulates retrying a failed transaction with the specified delay bucket.

        Parameters:
        -----------
        context: dict containing transaction features:
            - 'failure_code': str
            - 'bank': str
            - 'network': str
            - 'retry_attempt_number': int
            - 'day_of_month_bucket': str
            - 'customer_prior_success_count': str/int
            - 'customer_prior_failures_this_cycle': str/int
            - 'amount': float (optional, will be sampled if not provided)
            - 'simulated_day': int (optional, defaults to 1)
        delay: str, one of ('1hr', '6hr', '1d', '3d', '7d')

        Returns:
        --------
        (success: bool, amount_recovered: float)
            - success: True if the retry succeeded, False otherwise
            - amount_recovered: context['amount'] if success is True, else 0.0
        """
        if delay not in DELAY_ARMS:
            raise ValueError(f"Invalid delay arm: '{delay}'. Must be one of {DELAY_ARMS}")

        # Ensure transaction amount is present
        failure_code = context.get("failure_code", FailureCode.GENERIC_DECLINE.value)
        amount = context.get("amount")
        if amount is None or amount <= 0.0:
            amount = self.sample_amount(failure_code)
            context["amount"] = amount

        # Calculate true recovery probability
        p_recover = self.get_true_recovery_probability(context, delay)

        # Bernoulli trial
        success = bool(self.rng.random() < p_recover)
        amount_recovered = float(amount) if success else 0.0

        return success, amount_recovered

    @staticmethod
    def calculate_reward(
        success: bool,
        amount_recovered: float,
        retry_cost: float = DEFAULT_RETRY_COST,
    ) -> float:
        """
        Computes the net reward per Section 5 of the design doc:
        reward = (amount_recovered if success else 0) - retry_cost
        """
        return (amount_recovered if success else 0.0) - retry_cost


# Global simulator instance for functional interface
_global_simulator = RetrySimulator()


def simulate_retry(
    context: Dict[str, Any],
    delay: str,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[bool, float]:
    """
    Clean functional interface required by Phase 1:
    simulate_retry(context: dict, delay: str) -> (success: bool, amount_recovered: float)
    """
    if rng is not None:
        sim = RetrySimulator()
        sim.rng = rng
        return sim.simulate_retry(context, delay)
    return _global_simulator.simulate_retry(context, delay)
