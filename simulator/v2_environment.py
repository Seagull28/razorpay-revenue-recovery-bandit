"""
v2_environment.py
Pure, side-effect-free execution environment for the synthetic V2 payment retry simulator.

Exposes V2RetrySimulator.simulate_action(context, action) -> outcome_dict
"""

import zlib
from typing import Any, Dict, Optional, Tuple
import numpy as np

from bandit_retry_scheduler.core.recovery_action import RecoveryAction
from bandit_retry_scheduler.simulator.config import (
    AMOUNT_DISTRIBUTION_MAPPING,
    AMOUNT_DISTRIBUTION_PARAMS,
    DEFAULT_RETRY_COST,
    FailureCode,
)
from bandit_retry_scheduler.simulator.environment import get_deterministic_uniform
from bandit_retry_scheduler.simulator.v2_ground_truth import calculate_v2_recovery_probability

# Synthetic action cost assumptions (documented benchmark parameters)
V2_TIMED_RETRY_COST: float = 10.0      # INR per timing retry attempt
V2_METHOD_SWITCH_COST: float = 15.0    # INR per method switch prompt (SMS/notification/gateway switching overhead)


class V2RetrySimulator:
    """
    Pure synthetic simulator evaluating V2 RecoveryAction execution.
    Does NOT mutate caller context dictionaries.
    """

    def __init__(self, seed: Optional[int] = None):
        self.rng = np.random.default_rng(seed)

    def set_seed(self, seed: int) -> None:
        """Resets the random number generator with a specific seed."""
        self.rng = np.random.default_rng(seed)

    def sample_amount(self, failure_code: str) -> float:
        """Samples a transaction amount from a log-normal distribution conditioned on failure code."""
        dist_type = AMOUNT_DISTRIBUTION_MAPPING.get(failure_code, "standard")
        params = AMOUNT_DISTRIBUTION_PARAMS[dist_type]

        raw_amount = self.rng.lognormal(mean=params["mu"], sigma=params["sigma"])
        clipped_amount = max(params["min_amount"], min(params["max_amount"], raw_amount))
        return round(float(clipped_amount), 2)

    def get_true_recovery_probability(self, context: Dict[str, Any], action: RecoveryAction) -> float:
        """Returns the true ground-truth recovery probability for a V2 RecoveryAction."""
        return calculate_v2_recovery_probability(context, action)

    def simulate_action(
        self,
        context: Dict[str, Any],
        action: RecoveryAction,
        attempt_number: Optional[int] = None,
        evaluation_seed: Optional[int] = None,
        use_crn: bool = False,
    ) -> Dict[str, Any]:
        """
        Simulates executing a V2 RecoveryAction against the synthetic ground truth.

        PURE METHOD: Does NOT mutate the input context dictionary.

        Returns:
        --------
        Dict with keys:
        - action_id: str
        - action_type: str
        - source_method: str
        - target_method: str
        - delay: str
        - success: bool
        - amount_recovered: float
        - reward: float
        - action_cost: float
        """
        if not isinstance(context, dict):
            raise ValueError("Context must be a dictionary.")
        if not isinstance(action, RecoveryAction):
            raise TypeError("Action must be a RecoveryAction instance.")

        failure_code = context.get("failure_code", FailureCode.GENERIC_DECLINE.value)
        amount = context.get("amount")
        if amount is None or amount <= 0.0:
            amount = self.sample_amount(failure_code)

        # True recovery probability calculation
        p_recover = self.get_true_recovery_probability(context, action)

        # Bernoulli trial using action-independent CRN if enabled, else RNG
        if use_crn and evaluation_seed is not None:
            attempt = attempt_number or context.get("retry_attempt_number", 1)
            tx_id = str(context.get("transaction_id", "tx_default"))
            u = get_deterministic_uniform(evaluation_seed, tx_id, attempt)
            success = bool(u < p_recover)
        else:
            success = bool(self.rng.random() < p_recover)

        amount_recovered = float(amount) if success else 0.0

        # Action cost calculation
        action_cost = V2_METHOD_SWITCH_COST if action.action_type == "METHOD_SWITCH" else V2_TIMED_RETRY_COST
        reward = (amount_recovered - action_cost) if success else -action_cost

        return {
            "action_id": action.action_id,
            "action_type": action.action_type,
            "source_method": action.source_method,
            "target_method": action.target_method,
            "delay": action.delay,
            "success": success,
            "amount_recovered": round(amount_recovered, 2),
            "reward": round(reward, 2),
            "action_cost": action_cost,
        }
