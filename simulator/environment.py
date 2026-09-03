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


import zlib

def get_deterministic_uniform(seed: int, tx_id: str, attempt: int) -> float:
    """
    Derives a deterministic latent uniform value u in [0, 1) for paired Common Random Numbers (CRN) evaluation.
    u = deterministic_uniform(evaluation_seed, transaction_id, attempt_number)
    """
    key = f"{seed}:{tx_id}:{attempt}".encode("utf-8")
    crc = zlib.crc32(key) & 0xffffffff
    return crc / 4294967296.0


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
        self,
        context: Dict[str, Any],
        delay: str,
        attempt_number: Optional[int] = None,
        evaluation_seed: Optional[int] = None,
        use_crn: bool = False,
    ) -> Tuple[bool, float]:
        """
        Simulates retrying a failed transaction with the specified delay bucket.
        Supports Common Random Numbers (CRN) for fair paired policy evaluation.
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

        # Bernoulli trial using CRN if enabled, else RNG
        if use_crn and evaluation_seed is not None:
            attempt = attempt_number or context.get("retry_attempt_number", 1)
            tx_id = str(context.get("transaction_id", "tx_default"))
            u = get_deterministic_uniform(evaluation_seed, tx_id, attempt)
            success = bool(u < p_recover)
        else:
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
