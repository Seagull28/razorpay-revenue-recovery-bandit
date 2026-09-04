"""
test_scenario_robustness.py
Unit tests for Phase 4B ScenarioConfig, ScenarioAwareRetrySimulator, and ScenarioAwareStreamGenerator.
Verifies baseline equivalence, empirical failure-code weight shifts, scenario weight sum validity,
and numerical integrity of Phase 4B per-run and aggregate robustness outputs.
"""

import json
from pathlib import Path
import pytest

from bandit_retry_scheduler.simulator.config import DEFAULT_RETRY_COST
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
from bandit_retry_scheduler.run_phase4b_robustness import run_phase4b_robustness

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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
    txs = gen.generate_stream(num_days=20, transactions_per_day=100)  # 2000 txs
    assert len(txs) == 2000

    nsf_cnt = sum(1 for tx in txs if tx["failure_code"] == "insufficient_funds")
    share = nsf_cnt / len(txs)
    assert 0.55 <= share <= 0.65, f"Expected insufficient_funds share in [0.55, 0.65], got {share:.4f}"


def test_distribution_shift_empirical_share():
    """Test 3: Asserts DISTRIBUTION_SHIFT_SCENARIO empirical issuer_timeout share is between 0.37 and 0.47 for 2000 txs."""
    gen = ScenarioAwareStreamGenerator(config=DISTRIBUTION_SHIFT_SCENARIO, seed=42)
    txs = gen.generate_stream(num_days=20, transactions_per_day=100)  # 2000 txs
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


def test_phase4b_record_accounting_consistency():
    """Test A: Verifies every recorded Phase 4B run record satisfies mathematical retry cost and net revenue identities."""
    raw_file = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4b_robustness" / "phase4b_per_run_results.json"
    if not raw_file.exists():
        pytest.skip("Phase 4B per-run results artifact not yet generated")

    with open(raw_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    for r in records:
        attempts = r["total_attempts"]
        cost = r["total_retry_cost"]
        expected_cost = round(attempts * DEFAULT_RETRY_COST, 2)
        assert cost == expected_cost, (
            f"Scenario '{r['scenario_name']}', seed {r['seed']}, policy '{r['policy_name']}': "
            f"total_retry_cost ({cost}) != expected ({expected_cost}) from attempts ({attempts})"
        )

        gross = r["gross_recovered_revenue"]
        net = r["net_revenue"]
        expected_net = round(gross - cost, 2)
        assert abs(net - expected_net) < 0.01, (
            f"Scenario '{r['scenario_name']}', seed {r['seed']}, policy '{r['policy_name']}': "
            f"net_revenue ({net}) != expected ({expected_net}) from gross ({gross}) - cost ({cost})"
        )


def test_phase4b_average_attempts_consistency():
    """Test B: Verifies average_attempts_per_transaction matches total_attempts / transactions_total."""
    raw_file = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4b_robustness" / "phase4b_per_run_results.json"
    if not raw_file.exists():
        pytest.skip("Phase 4B per-run results artifact not yet generated")

    with open(raw_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    for r in records:
        attempts = r["total_attempts"]
        total_txs = r["transactions_total"]
        reported_avg = r["average_attempts_per_transaction"]
        expected_avg = round(attempts / total_txs, 4) if total_txs > 0 else 0.0
        assert reported_avg == expected_avg, (
            f"Scenario '{r['scenario_name']}', seed {r['seed']}, policy '{r['policy_name']}': "
            f"average_attempts_per_transaction ({reported_avg}) != expected ({expected_avg})"
        )


def test_phase4b_aggregate_mean_consistency():
    """Test C: Verifies summary aggregate means match direct recomputations from raw per-seed records."""
    raw_file = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4b_robustness" / "phase4b_per_run_results.json"
    summary_file = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4b_robustness" / "phase4b_summary.json"
    if not (raw_file.exists() and summary_file.exists()):
        pytest.skip("Phase 4B artifacts not yet generated")

    with open(raw_file, "r", encoding="utf-8") as f:
        records = json.load(f)
    with open(summary_file, "r", encoding="utf-8") as f:
        summary = json.load(f)

    for sc_name, sc_data in summary["scenarios"].items():
        for pname, p_summary in sc_data["policies"].items():
            matching = [r for r in records if r["scenario_name"] == sc_name and r["policy_name"] == pname]
            assert len(matching) > 0, f"No raw records found for scenario '{sc_name}', policy '{pname}'"

            recomputed_net = round(sum(r["net_revenue"] for r in matching) / len(matching), 2)
            reported_net = p_summary["mean_net_revenue_inr"]
            assert abs(reported_net - recomputed_net) < 0.01, (
                f"Scenario '{sc_name}', policy '{pname}': mean_net_revenue_inr ({reported_net}) "
                f"!= recomputed ({recomputed_net})"
            )

            recomputed_cost = round(sum(r["total_retry_cost"] for r in matching) / len(matching), 2)
            reported_cost = p_summary["mean_retry_cost_inr"]
            assert abs(reported_cost - recomputed_cost) < 0.01, (
                f"Scenario '{sc_name}', policy '{pname}': mean_retry_cost_inr ({reported_cost}) "
                f"!= recomputed ({recomputed_cost})"
            )


def test_phase4b_fresh_run_isolated_integrity(tmp_path):
    """Test D: Executes Phase 4B runner in tmp_path and verifies output accounting integrity."""
    summary = run_phase4b_robustness(output_dir=tmp_path)
    assert "scenarios" in summary

    raw_path = tmp_path / "phase4b_per_run_results.json"
    assert raw_path.exists()

    with open(raw_path, "r", encoding="utf-8") as f:
        fresh_records = json.load(f)

    assert len(fresh_records) == 18  # 3 scenarios * 2 policies * 3 seeds
    for r in fresh_records:
        assert r["total_retry_cost"] == round(r["total_attempts"] * DEFAULT_RETRY_COST, 2)
        assert abs(r["net_revenue"] - round(r["gross_recovered_revenue"] - r["total_retry_cost"], 2)) < 0.01
