"""
test_risk_intelligence.py
Unit tests for core/risk.py Risk-Aware Recovery Intelligence Engine.
"""

import pytest
from bandit_retry_scheduler.core.risk import (
    StrategyMode,
    RiskLevel,
    compute_risk_profile,
    evaluate_risk_aware_recommendation,
)


def test_risk_profile_bounds():
    transaction = {"failure_code": "insufficient_funds"}
    arm_scores = {"1d": {"score": 10.0}, "3d": {"score": 12.0}}
    profile = compute_risk_profile(transaction, arm_scores, attempt_number=1)
    
    assert 0.0 <= profile.risk_score <= 1.0
    assert profile.risk_level in [r.value for r in RiskLevel]
    assert isinstance(profile.risk_factors, list)
    assert profile.decision_stability in ["STABLE", "MODERATELY_STABLE", "UNSTABLE"]


def test_maximize_recovery_preserves_raw():
    arm_scores = {"1hr": {"score": 5.0}, "3d": {"score": 15.0}}
    tx = {"failure_code": "issuer_timeout"}
    arm, profile, meta = evaluate_risk_aware_recommendation(
        arm_scores, raw_selected_arm="3d", transaction=tx, strategy_mode="MAXIMIZE_RECOVERY"
    )
    assert arm == "3d"
    assert meta["mode"] == "MAXIMIZE_RECOVERY"


def test_conservative_mode_behavior():
    arm_scores = {"1hr": {"score": 10.0}, "1d": {"score": 9.9}, "3d": {"score": 9.8}}
    tx = {"failure_code": "insufficient_funds"}
    arm, profile, meta = evaluate_risk_aware_recommendation(
        arm_scores, raw_selected_arm="1hr", transaction=tx, strategy_mode="CONSERVATIVE", attempt_number=2
    )
    assert isinstance(arm, str)
    assert "mode" in meta
