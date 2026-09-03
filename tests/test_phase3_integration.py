"""
test_phase3_integration.py
End-to-end integration tests for Phase 3 Recovery Intelligence API,
schema validation, backward compatibility, report/JSON consistency, and ground-truth isolation.
"""

import json
from pathlib import Path
import pytest
from bandit_retry_scheduler.api.intelligence_service import (
    get_recovery_intelligence,
    SIMULATION_DISCLOSURE,
)
from bandit_retry_scheduler.api.decision_service import get_retry_decision
from bandit_retry_scheduler.analytics.recovery_insights import generate_merchant_recovery_insights
from bandit_retry_scheduler.core.risk import evaluate_risk_aware_recommendation


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


def test_phase3_report_json_consistency():
    summary_path = Path("audit/evaluation_results/phase3/phase3_summary.json")
    report_path = Path("audit/evaluation_results/phase3/PHASE3_EVALUATION_REPORT.md")

    if not summary_path.exists() or not report_path.exists():
        pytest.skip("Phase 3 evaluation artifacts not generated yet.")

    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    report = report_path.read_text(encoding="utf-8")

    # Assert top arms and shift rates match between JSON and Report
    for mode in summary["strategy_modes_evaluated"]:
        m_data = summary["metrics"][mode]
        top_arm = m_data["top_strategy_arm"]
        shift_pct = f"{m_data['mode_shift_rate_vs_raw'] * 100:.1f}%"
        
        assert top_arm in report, f"Top arm {top_arm} for {mode} not found in report!"
        assert shift_pct in report, f"Shift pct {shift_pct} for {mode} not found in report!"


def test_insights_record_override():
    # Verify fallback vs dynamic eval_records override
    demo_insights = generate_merchant_recovery_insights(eval_records=None)
    assert demo_insights["is_demo_fallback"] is True
    assert "DEMO SAMPLE DATA" in demo_insights["synthetic_data_notice"]

    eval_records = [
        {
            "failure_code": "issuer_timeout",
            "should_retry": True,
            "expected_net_value_inr": 150.0,
            "recommendation": {"strategy": "IMMEDIATE_RECOVERY", "retry_delay": "1hr"},
        },
        {
            "failure_code": "insufficient_funds",
            "should_retry": True,
            "expected_net_value_inr": 200.0,
            "recommendation": {"strategy": "PATIENT_RECOVERY", "retry_delay": "3d"},
        },
    ]
    dynamic_insights = generate_merchant_recovery_insights(eval_records=eval_records)
    assert dynamic_insights["is_demo_fallback"] is False
    assert dynamic_insights["total_transactions_analyzed"] == 2
    assert "Synthetic simulation insight" in dynamic_insights["synthetic_data_notice"]


def test_controlled_score_vector_modes():
    # Controlled artificial score vectors
    scores = {
        "1hr": {"score": 100.0},
        "6hr": {"score": 90.0},
        "1d": {"score": 80.0},
        "3d": {"score": 70.0},
        "7d": {"score": 60.0},
    }
    tx = {"failure_code": "issuer_timeout"}
    
    arm_max, _, _ = evaluate_risk_aware_recommendation(scores, "1hr", tx, strategy_mode="MAXIMIZE_RECOVERY")
    assert arm_max == "1hr"

    arm_bal, _, _ = evaluate_risk_aware_recommendation(scores, "1hr", tx, strategy_mode="BALANCED")
    assert arm_bal == "1hr"


def test_diagnostics_artifact_schema():
    diag_path = Path("audit/evaluation_results/phase3/phase3_mode_diagnostics.json")
    if not diag_path.exists():
        pytest.skip("Diagnostics artifact not generated yet.")

    with open(diag_path, "r", encoding="utf-8") as f:
        diag = json.load(f)

    assert "sample_size" in diag
    assert "summary_statistics" in diag
    assert "first_10_transactions_detail" in diag
    assert len(diag["first_10_transactions_detail"]) == 10
