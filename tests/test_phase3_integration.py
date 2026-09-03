"""
test_phase3_integration.py
End-to-end integration tests for Phase 3 Recovery Intelligence API,
schema validation, backward compatibility, and ground-truth isolation.
"""

import json
import pytest
from bandit_retry_scheduler.api.intelligence_service import (
    get_recovery_intelligence,
    SIMULATION_DISCLOSURE,
)
from bandit_retry_scheduler.api.decision_service import get_retry_decision


def test_get_recovery_intelligence_schema():
    sample_tx = {
        "transaction_id": "txn_phase3_test_1",
        "amount": 2500.0,
        "failure_code": "insufficient_funds",
        "bank": "Bank A",
        "network": "Visa",
        "attempt_number": 1,
        "day_of_month": 5,
        "hour_of_day": 14,
    }
    
    res = get_recovery_intelligence(sample_tx, strategy_mode="BALANCED")
    
    assert res["transaction_id"] == "txn_phase3_test_1"
    assert res["strategy_mode"] == "BALANCED"
    assert "should_retry" in res
    assert "recommendation" in res
    assert "confidence" in res
    assert 0.0 <= res["confidence"]["score"] <= 1.0
    assert "decision_stability" in res
    assert "risk_profile" in res
    assert "alternatives" in res
    assert len(res["alternatives"]) == 5
    assert "explanation" in res
    assert res["simulation_disclosure"] == SIMULATION_DISCLOSURE
    
    # Assert JSON serializable
    json_str = json.dumps(res)
    assert len(json_str) > 0


def test_backward_compatibility_get_retry_decision():
    sample_tx = {
        "transaction_id": "txn_phase3_test_2",
        "amount": 1000.0,
        "failure_code": "issuer_timeout",
        "bank": "Bank B",
        "network": "Mastercard",
        "attempt_number": 1,
    }
    
    res_legacy = get_retry_decision(sample_tx)
    assert "transaction_id" in res_legacy
    assert "should_retry" in res_legacy
    assert "recommended_delay" in res_legacy
    assert "expected_net_value_inr" in res_legacy
    assert "explanation" in res_legacy
