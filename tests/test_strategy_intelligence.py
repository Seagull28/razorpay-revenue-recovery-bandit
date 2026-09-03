"""
test_strategy_intelligence.py
Unit tests for core/strategy.py Recovery Strategy Intelligence Engine.
"""

import pytest
from bandit_retry_scheduler.core.strategy import (
    StrategyCategory,
    RETRY_ARM_TO_STRATEGY,
    get_strategy_category,
    get_strategy_metadata,
    calculate_decision_confidence,
    classify_decision_stability,
    get_alternative_strategies,
    STABLE_THRESHOLD,
    MODERATE_THRESHOLD,
)


def test_strategy_category_mapping():
    assert get_strategy_category("1hr") == StrategyCategory.IMMEDIATE_RECOVERY
    assert get_strategy_category("6hr") == StrategyCategory.FAST_RETRY
    assert get_strategy_category("1d") == StrategyCategory.BALANCED_RETRY
    assert get_strategy_category("3d") == StrategyCategory.PATIENT_RECOVERY
    assert get_strategy_category("7d") == StrategyCategory.LAST_CHANCE_RECOVERY
    assert get_strategy_category("invalid") == StrategyCategory.BALANCED_RETRY


def test_strategy_metadata():
    meta = get_strategy_metadata("3d")
    assert meta["strategy"] == "PATIENT_RECOVERY"
    assert meta["retry_delay"] == "3d"
    assert "title" in meta
    assert "description" in meta


def test_decision_confidence_bounds():
    arm_scores = {
        "1hr": {"score": 10.0},
        "6hr": {"score": 15.0},
        "1d": {"score": 25.0},
        "3d": {"score": 50.0},
        "7d": {"score": 20.0},
    }
    conf, interp = calculate_decision_confidence(arm_scores)
    assert 0.0 <= conf <= 1.0
    assert isinstance(interp, str)


def test_decision_stability_classification():
    assert classify_decision_stability(0.8, score_gap=0.20) == "STABLE"
    assert classify_decision_stability(0.3, score_gap=0.08) == "MODERATELY_STABLE"
    assert classify_decision_stability(0.1, score_gap=0.02) == "UNSTABLE"


def test_alternative_strategies_ranking():
    arm_scores = {
        "1hr": {"score": 10.0},
        "6hr": {"score": 15.0},
        "1d": {"score": 25.0},
        "3d": {"score": 50.0},
        "7d": {"score": 20.0},
    }
    alts = get_alternative_strategies(arm_scores, selected_arm="3d")
    assert len(alts) == 5
    assert alts[0]["retry_delay"] == "3d"
    assert alts[0]["rank"] == 1
    assert alts[0]["is_selected"] is True
    assert alts[1]["retry_delay"] == "1d"
    assert alts[1]["rank"] == 2
