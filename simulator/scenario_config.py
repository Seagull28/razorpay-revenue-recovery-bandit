"""
scenario_config.py
Configuration dataclass and pre-defined environmental stress scenarios for Phase 4B Robustness Evaluation.
"""

from dataclasses import dataclass
from typing import Optional, Dict


@dataclass
class ScenarioConfig:
    name: str
    description: str
    recovery_probability_multiplier: float = 1.0
    transaction_amount_multiplier: float = 1.0
    failure_code_weight_overrides: Optional[Dict[str, float]] = None
    # failure_code_weight_overrides, if provided, REPLACES
    # TransactionStreamGenerator.failure_code_weights entirely (must sum to 1.0).
    # If None, original baseline weights are used unchanged.


BASELINE_SCENARIO = ScenarioConfig(
    name="baseline",
    description="Reference environment — identical to existing Phase 1 simulation "
                 "(multipliers = 1.0, no weight overrides). Used to prove the wrapper "
                 "introduces zero behavioral change when neutral.",
)

HIGH_INSUFFICIENT_FUNDS_SCENARIO = ScenarioConfig(
    name="high_insufficient_funds",
    description="Insufficient-funds failures increased from 38% to 60% baseline share; "
                 "remaining share redistributed proportionally across other failure codes.",
    failure_code_weight_overrides={
        "insufficient_funds": 0.60,
        "issuer_timeout": 0.16,
        "generic_decline": 0.12,
        "do_not_honor": 0.08,
        "card_expired": 0.04,
    },
)

DISTRIBUTION_SHIFT_SCENARIO = ScenarioConfig(
    name="distribution_shift",
    description="Failure-code mix inverted relative to baseline (issuer_timeout becomes "
                 "dominant instead of insufficient_funds) combined with a 30% reduction "
                 "in overall recovery probability, simulating a harsher, structurally "
                 "different production environment than the one policies were tuned on.",
    recovery_probability_multiplier=0.70,
    failure_code_weight_overrides={
        "insufficient_funds": 0.18,
        "issuer_timeout": 0.42,
        "generic_decline": 0.20,
        "do_not_honor": 0.14,
        "card_expired": 0.06,
    },
)
