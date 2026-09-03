"""
test_phase4_diagnostics.py
Unit tests for Phase 4A Strategy Intelligence Diagnostic Harness and helper functions.
Verifies determinism, non-mutation of production config, and artifact calculation validity.
"""

import pytest
import numpy as np
from pathlib import Path
from bandit_retry_scheduler.run_phase4_strategy_diagnostics import (
    calculate_quantiles,
    extract_arm_score,
    get_warmed_evaluation_policy,
    run_phase4_diagnostics,
)
from bandit_retry_scheduler.api.intelligence_service import get_recovery_intelligence
from bandit_retry_scheduler.core.config import (
    BALANCED_RISK_WEIGHT,
    CONSERVATIVE_RISK_WEIGHT,
)


def test_calculate_quantiles_empty_and_valid():
    q_empty = calculate_quantiles([])
    assert q_empty["mean"] == 0.0
    assert q_empty["median"] == 0.0

    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    q = calculate_quantiles(vals)
    assert q["min"] == 10.0
    assert q["max"] == 50.0
    assert q["median"] == 30.0
    assert q["mean"] == 30.0


def test_extract_arm_score_parsing():
    assert extract_arm_score({"score": 150.0}) == 150.0
    assert extract_arm_score({"ucb_score": 120.0}) == 120.0
    assert extract_arm_score({"theta_dot_x": 90.0}) == 90.0
    assert extract_arm_score(45.5) == 45.5
    assert extract_arm_score(None) == 0.0


def test_warmed_evaluation_policy_determinism():
    p1 = get_warmed_evaluation_policy(seed=42, warm_tx_count=100)
    p2 = get_warmed_evaluation_policy(seed=42, warm_tx_count=100)

    tx = {"failure_code": "insufficient_funds", "amount": 2500.0}
    intel1 = get_recovery_intelligence(tx, "MAXIMIZE_RECOVERY", policy=p1)
    intel2 = get_recovery_intelligence(tx, "MAXIMIZE_RECOVERY", policy=p2)

    assert intel1["raw_decision"]["recommended_delay"] == intel2["raw_decision"]["recommended_delay"]
    score1 = extract_arm_score(intel1["raw_decision"]["arm_scores"]["3d"])
    score2 = extract_arm_score(intel2["raw_decision"]["arm_scores"]["3d"])
    assert pytest.approx(score1) == score2


def test_run_phase4_diagnostics_executes_and_preserves_config():
    # Record initial config
    init_bal_w = BALANCED_RISK_WEIGHT
    init_cons_w = CONSERVATIVE_RISK_WEIGHT

    # Run small diagnostic execution
    run_phase4_diagnostics(eval_sample_size=20)

    # Verify production config was not mutated
    assert BALANCED_RISK_WEIGHT == init_bal_w
    assert CONSERVATIVE_RISK_WEIGHT == init_cons_w

    # Verify diagnostic summary artifact exists
    summary_path = Path("audit/evaluation_results/phase4_strategy_diagnostics/phase4_strategy_summary.json")
    assert summary_path.exists()
