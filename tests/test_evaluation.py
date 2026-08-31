"""
test_evaluation.py
Unit and integration tests for Phase 4 evaluation harness, metrics, and visualization modules.
"""

from pathlib import Path
import os
import pytest

from bandit_retry_scheduler.evaluation.harness import EvaluationHarness
from bandit_retry_scheduler.evaluation.metrics import (
    compute_cold_start_metrics,
    compute_drift_adaptation_metrics,
    compute_oracle_regret,
    compute_performance_by_segment,
)


def test_compute_performance_by_segment():
    dummy_records = [
        {
            "transaction_id": "tx_1",
            "context_vector": {"failure_code": "insufficient_funds", "bank": "Bank A"},
            "actual_outcome": 1,
            "amount_recovered": 1000.0,
            "reward": 990.0,
        },
        {
            "transaction_id": "tx_1",
            "context_vector": {"failure_code": "insufficient_funds", "bank": "Bank A"},
            "actual_outcome": 0,
            "amount_recovered": 0.0,
            "reward": -10.0,
        },
    ]

    res = compute_performance_by_segment(dummy_records)
    assert res["overall"]["total_tx"] == 1
    assert res["overall"]["recovered_tx"] == 1
    assert res["overall"]["recovery_rate_pct"] == 100.0
    assert res["overall"]["gross_revenue"] == 1000.0
    assert res["overall"]["retry_cost"] == 20.0
    assert res["overall"]["net_revenue"] == 980.0


def test_oracle_regret_sublinearity():
    harness = EvaluationHarness(seeds=[42], num_days=5, transactions_per_day=20)
    seed_res = harness.run_seed_benchmark(42)
    regret_data = seed_res["regret_data"]

    cum_exp = regret_data["cum_regret_expected"]
    assert len(cum_exp) > 0
    # Expected regret should be non-negative
    assert regret_data["final_cum_regret_expected"] >= 0.0
    # Regret growth per step should drop over time (sublinear)
    mid_idx = len(cum_exp) // 2
    early_avg_regret = cum_exp[mid_idx] / mid_idx
    total_avg_regret = cum_exp[-1] / len(cum_exp)
    assert total_avg_regret <= early_avg_regret * 1.5


def test_harness_full_evaluation_and_plot_creation(tmp_path):
    plots_dir = tmp_path / "plots"
    harness = EvaluationHarness(seeds=[42], num_days=2, transactions_per_day=10)
    res = harness.run_full_evaluation(output_plots_dir=str(plots_dir))

    assert "per_seed_results" in res
    assert 42 in res["per_seed_results"]
    plots = res["plots_generated"]
    assert "regret_curve" in plots
    assert "convergence_plots" in plots
    assert "cold_start_comparison" in plots
    assert "drift_adaptation" in plots

    for key, path in plots.items():
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0
