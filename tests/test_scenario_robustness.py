"""
test_scenario_robustness.py
Unit tests for Phase 4B ScenarioConfig, ScenarioAwareRetrySimulator, and ScenarioAwareStreamGenerator.
Verifies baseline equivalence, empirical failure-code weight shifts, and scenario weight sum validity.
"""

import pytest
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.scenario_config import (
    BASELINE_SCENARIO,
    HIGH_INSUFFICIENT_FUNDS_SCENARIO,
    DISTRIBUTION_SHIFT_SCENARIO,
    ScenarioConfig,
)
from bandit_retry_scheduler.simulator.scenario_environment import (
    ScenarioAwareRetrySimulator,
    ScenarioAwareStreamGenerator,
)


def test_baseline_equivalence():
    """Test 1: Asserts ScenarioAwareRetrySimulator with BASELINE_SCENARIO is bit-identical to RetrySimulator."""
    sim_base = RetrySimulator(seed=42)
    sim_scenario = ScenarioAwareRetrySimulator(config=BASELINE_SCENARIO, seed=42)

    sample_context = {
        "failure_code": "insufficient_funds",
        "bank": "Bank A",
        "network": "Visa",
        "retry_attempt_number": 1,
        "day_of_month_bucket": "1-5",
        "customer_prior_success_count": "1-3",
        "customer_prior_failures_this_cycle": "0",
        "amount": 2500.0,
    }

    # Verify probability equivalence across all arms
    for arm in ["1hr", "6hr", "1d", "3d", "7d"]:
        p1 = sim_base.get_true_recovery_probability(sample_context, arm)
        p2 = sim_scenario.get_true_recovery_probability(sample_context, arm)
        assert p1 == p2, f"Probability mismatch for arm {arm}: {p1} vs {p2}"

    # Verify amount sampling equivalence
    amt1 = sim_base.sample_amount("insufficient_funds")
    amt2 = sim_scenario.sample_amount("insufficient_funds")
    assert amt1 == amt2, f"Amount mismatch: {amt1} vs {amt2}"


def test_high_insufficient_funds_empirical_share():
    """Test 2: Asserts HIGH_INSUFFICIENT_FUNDS_SCENARIO empirical share is between 0.55 and 0.65 for 2000 txs."""
    gen = ScenarioAwareStreamGenerator(config=HIGH_INSUFFICIENT_FUNDS_SCENARIO, seed=42)
    txs = gen.generate_stream(num_days=20, transactions_per_day=100) # 2000 txs
    assert len(txs) == 2000

    nsf_cnt = sum(1 for tx in txs if tx["failure_code"] == "insufficient_funds")
    share = nsf_cnt / len(txs)
    assert 0.55 <= share <= 0.65, f"Expected insufficient_funds share in [0.55, 0.65], got {share:.4f}"


def test_distribution_shift_empirical_share():
    """Test 3: Asserts DISTRIBUTION_SHIFT_SCENARIO empirical issuer_timeout share is between 0.37 and 0.47 for 2000 txs."""
    gen = ScenarioAwareStreamGenerator(config=DISTRIBUTION_SHIFT_SCENARIO, seed=42)
    txs = gen.generate_stream(num_days=20, transactions_per_day=100) # 2000 txs
    assert len(txs) == 2000

    timeout_cnt = sum(1 for tx in txs if tx["failure_code"] == "issuer_timeout")
    share = timeout_cnt / len(txs)
    assert 0.37 <= share <= 0.47, f"Expected issuer_timeout share in [0.37, 0.47], got {share:.4f}"


def test_scenario_configs_weight_sums():
    """Test 4: Asserts all defined ScenarioConfigs have failure_code_weight_overrides summing to 1.0 (or None)."""
    scenarios = [BASELINE_SCENARIO, HIGH_INSUFFICIENT_FUNDS_SCENARIO, DISTRIBUTION_SHIFT_SCENARIO]
    for sc in scenarios:
        if sc.failure_code_weight_overrides is not None:
            total = sum(sc.failure_code_weight_overrides.values())
            assert abs(total - 1.0) < 1e-6, f"Scenario '{sc.name}' weights sum to {total}, expected 1.0"
