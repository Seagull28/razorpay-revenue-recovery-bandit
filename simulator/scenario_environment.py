"""
scenario_environment.py
Scenario-aware simulator wrappers for Phase 4B Robustness Evaluation.
Wraps RetrySimulator and TransactionStreamGenerator to apply ScenarioConfig multipliers
without modifying existing simulator codebase files.
"""

from typing import Any, Dict, Optional
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator
from bandit_retry_scheduler.simulator.scenario_config import ScenarioConfig


class ScenarioAwareRetrySimulator(RetrySimulator):
    """
    Wraps RetrySimulator to apply ScenarioConfig multipliers WITHOUT modifying
    ground_truth.py or environment.py. When config has multiplier=1.0 (baseline),
    behavior must be bit-identical to the parent class for the same seed.
    """

    def __init__(self, config: ScenarioConfig, seed: Optional[int] = None):
        super().__init__(seed=seed)
        self.config = config

    def get_true_recovery_probability(self, context: Dict[str, Any], delay: str) -> float:
        base_p = super().get_true_recovery_probability(context, delay)
        scaled = base_p * self.config.recovery_probability_multiplier
        return float(max(0.0, min(1.0, scaled)))

    def sample_amount(self, failure_code: str) -> float:
        base_amount = super().sample_amount(failure_code)
        return round(base_amount * self.config.transaction_amount_multiplier, 2)


class ScenarioAwareStreamGenerator(TransactionStreamGenerator):
    """
    Wraps TransactionStreamGenerator to apply failure-code weight overrides and to
    inject a ScenarioAwareRetrySimulator for amount sampling, WITHOUT modifying
    stream_generator.py.
    """

    def __init__(self, config: ScenarioConfig, seed: Optional[int] = 42):
        super().__init__(seed=seed)
        self.config = config
        if config.failure_code_weight_overrides is not None:
            total = sum(config.failure_code_weight_overrides.values())
            assert abs(total - 1.0) < 1e-6, (
                f"failure_code_weight_overrides for scenario '{config.name}' sums to "
                f"{total}, must sum to 1.0"
            )
            self.failure_code_weights = dict(config.failure_code_weight_overrides)
        # Replace the plain simulator with a scenario-aware one so amount sampling
        # during generate_transaction() also respects the config.
        self.simulator = ScenarioAwareRetrySimulator(config=config, seed=seed)
