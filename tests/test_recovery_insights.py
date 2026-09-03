"""
test_recovery_insights.py
Unit tests for analytics/recovery_insights.py Merchant Insights Engine.
"""

import pytest
from bandit_retry_scheduler.analytics.recovery_insights import (
    calculate_opportunity_score,
    generate_merchant_recovery_insights,
    ANALYTICS_DISCLOSURE,
)


def test_opportunity_score_bounds():
    assert calculate_opportunity_score(0, 0.5, 100.0) == 0.0
    assert 0.0 <= calculate_opportunity_score(50, 0.8, 250.0) <= 100.0
    assert calculate_opportunity_score(500, 1.0, 1000.0) == 100.0


def test_generate_merchant_insights_baseline():
    insights = generate_merchant_recovery_insights()
    assert "overall_recovery_rate" in insights
    assert "total_transactions_analyzed" in insights
    assert "highest_opportunity_segment" in insights
    assert "segments" in insights
    assert len(insights["segments"]) >= 4
    assert insights["synthetic_data_notice"] == ANALYTICS_DISCLOSURE


def test_generate_merchant_insights_with_records():
    records = [
        {"failure_code": "insufficient_funds", "recovered": True, "reward": 100.0},
        {"failure_code": "insufficient_funds", "recovered": False, "reward": -10.0},
        {"failure_code": "issuer_timeout", "recovered": True, "reward": 150.0},
    ]
    insights = generate_merchant_recovery_insights(records)
    assert insights["total_transactions_analyzed"] == 3
    assert len(insights["segments"]) == 2
