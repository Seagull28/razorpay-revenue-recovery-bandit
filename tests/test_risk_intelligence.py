"""
test_risk_intelligence.py
Unit tests for core/risk.py Risk-Aware Strategy Engine and dimensionless friction models.
"""

import pytest
from bandit_retry_scheduler.core.risk import (
    compute_risk_profile,
    evaluate_risk_aware_recommendation,
    StrategyMode,
    RiskLevel,
    ARM_RISK_PROFILE,
    EXTREME_ARM_FRICTION,
)
from bandit_retry_scheduler.core.config import (
    MIN_CONFIDENCE_SCALE,
    BALANCED_RISK_WEIGHT,
    CONSERVATIVE_RISK_WEIGHT,
)


def test_risk_profile_bounds():
    tx = {"failure_code": "insufficient_funds"}
    scores = {"1d": 100.0, "3d": 90.0}
    prof = compute_risk_profile(tx, scores, attempt_number=1)
    assert 0.0 <= prof.risk_score <= 1.0
    assert prof.risk_level in (RiskLevel.LOW.value, RiskLevel.MEDIUM.value, RiskLevel.HIGH.value)
    assert isinstance(prof.risk_factors, list)


def test_maximize_recovery_preserves_raw():
    scores = {"1hr": 200.0, "3d": 150.0}
    tx = {"failure_code": "generic_decline"}
    arm, prof, meta = evaluate_risk_aware_recommendation(scores, "1hr", tx, strategy_mode="MAXIMIZE_RECOVERY")
    assert arm == "1hr"
    assert meta["mode"] == "MAXIMIZE_RECOVERY"


def test_conservative_mode_behavior():
    scores = {"1hr": 105.0, "3d": 100.0}
    tx = {"failure_code": "insufficient_funds"}
    arm, prof, meta = evaluate_risk_aware_recommendation(scores, "1hr", tx, strategy_mode="CONSERVATIVE")
    assert meta["mode"] == "CONSERVATIVE"
    assert "adjusted_scores" in meta


def test_no_fixed_inr_penalties_behavioral_proportional_scaling():
    """
    Verifies that zero fixed INR penalties exist and that risk adjustments
    scale 100% proportionally when score vectors are multiplied by a scalar c.
    """
    scores_small = {"1hr": 1000.0, "3d": 900.0}
    scores_large = {"1hr": 10000.0, "3d": 9000.0}
    tx = {"failure_code": "insufficient_funds"}

    _, _, meta_small = evaluate_risk_aware_recommendation(scores_small, "1hr", tx, strategy_mode="CONSERVATIVE")
    _, _, meta_large = evaluate_risk_aware_recommendation(scores_large, "1hr", tx, strategy_mode="CONSERVATIVE")

    adj_small = meta_small["adjusted_scores"]
    adj_large = meta_large["adjusted_scores"]

    # Ratio of adjusted scores must equal ratio of input scores (10.0)
    ratio_1hr = adj_large["1hr"] / adj_small["1hr"]
    ratio_3d = adj_large["3d"] / adj_small["3d"]

    assert pytest.approx(ratio_1hr, rel=1e-3) == 10.0
    assert pytest.approx(ratio_3d, rel=1e-3) == 10.0


def test_strategy_mode_divergence_under_uncertainty():
    """
    Verifies that high confidence scenarios converge naturally across modes,
    and low confidence close-score scenarios diverge legitimately.
    """
    tx = {"failure_code": "insufficient_funds"}

    # High confidence -> zero divergence
    scores_high_conf = {"3d": 1500.0, "1d": 800.0, "1hr": 400.0}
    arm_max_h, _, _ = evaluate_risk_aware_recommendation(scores_high_conf, "3d", tx, "MAXIMIZE_RECOVERY")
    arm_bal_h, _, _ = evaluate_risk_aware_recommendation(scores_high_conf, "3d", tx, "BALANCED")
    arm_cons_h, _, _ = evaluate_risk_aware_recommendation(scores_high_conf, "3d", tx, "CONSERVATIVE")

    assert arm_max_h == arm_bal_h == arm_cons_h == "3d", "High confidence decisions must converge!"

    # Low confidence close scores -> legitimate divergence
    scores_low_conf = {"1hr": 1000.0, "6hr": 990.0, "1d": 980.0, "3d": 970.0, "7d": 960.0}
    arm_max_l, _, _ = evaluate_risk_aware_recommendation(scores_low_conf, "1hr", tx, "MAXIMIZE_RECOVERY")
    arm_bal_l, _, _ = evaluate_risk_aware_recommendation(scores_low_conf, "1hr", tx, "BALANCED")
    arm_cons_l, _, _ = evaluate_risk_aware_recommendation(scores_low_conf, "1hr", tx, "CONSERVATIVE")

    assert arm_max_l == "1hr"
    assert arm_bal_l == "3d" or arm_cons_l == "3d"
    assert len({arm_max_l, arm_bal_l, arm_cons_l}) > 1, "Low confidence close scores must demonstrate mode divergence!"
