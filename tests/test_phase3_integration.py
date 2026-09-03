"""
test_phase3_integration.py
End-to-end integration tests for Phase 3 Recovery Intelligence API,
schema validation, backward compatibility, report/JSON consistency,
warmed-policy evaluation, strategy mode fairness, deterministic tie-breaking,
policy update executed arm correctness, and scale-aware confidence.
"""

import json
from pathlib import Path
import pytest
from bandit_retry_scheduler.api.intelligence_service import (
    get_recovery_intelligence,
    SIMULATION_DISCLOSURE,
)
from bandit_retry_scheduler.api.decision_service import get_retry_decision
from bandit_retry_scheduler.api.action_executor import execute_retry_action
from bandit_retry_scheduler.api.feedback_loop import process_outcome_and_update
from bandit_retry_scheduler.analytics.recovery_insights import generate_merchant_recovery_insights
from bandit_retry_scheduler.core.risk import evaluate_risk_aware_recommendation
from bandit_retry_scheduler.core.strategy import (
    calculate_decision_confidence,
    classify_decision_stability,
)
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.run_phase3_evaluation import get_warmed_evaluation_policy


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
    assert "raw_policy_arm" in res
    assert "final_recommended_arm" in res
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


def test_phase3_warmed_policy_score_variation():
    policy = get_warmed_evaluation_policy(seed=42, warm_tx_count=200)
    tx = {
        "transaction_id": "txn_warm_val",
        "amount": 3500.0,
        "failure_code": "issuer_timeout",
        "bank": "Bank B",
        "network": "Visa",
        "attempt_number": 1,
    }
    
    scores = policy.get_arm_scores(tx)
    ucb_scores = [d["ucb_score"] for d in scores.values()]
    ucb_scores.sort(reverse=True)
    
    raw_gap = ucb_scores[0] - ucb_scores[1]
    assert raw_gap > 0.0, "Warmed policy must produce non-zero score gap!"


def test_mode_fairness_identical_raw_scores():
    policy = get_warmed_evaluation_policy(seed=42, warm_tx_count=100)
    tx = {
        "transaction_id": "txn_fairness_val",
        "amount": 2000.0,
        "failure_code": "insufficient_funds",
        "bank": "Bank C",
        "network": "Mastercard",
        "attempt_number": 1,
    }

    res_max = get_recovery_intelligence(tx, strategy_mode="MAXIMIZE_RECOVERY", policy=policy)
    res_bal = get_recovery_intelligence(tx, strategy_mode="BALANCED", policy=policy)
    res_cons = get_recovery_intelligence(tx, strategy_mode="CONSERVATIVE", policy=policy)

    raw_max_arm = res_max["raw_decision"]["recommended_delay"]
    raw_bal_arm = res_bal["raw_decision"]["recommended_delay"]
    raw_cons_arm = res_cons["raw_decision"]["recommended_delay"]

    assert raw_max_arm == raw_bal_arm == raw_cons_arm, "All strategy modes must receive identical raw policy recommendations!"


def test_strategy_selected_arm_updates_correct_policy_arm():
    policy = LinUCBPolicy(alpha=1.0)
    simulator = RetrySimulator(seed=42)
    audit_logger = AuditLogger()

    sample_tx = {
        "transaction_id": "txn_update_arm_check",
        "amount": 5000.0,
        "failure_code": "insufficient_funds",
        "bank": "Bank A",
        "network": "Visa",
        "attempt_number": 1,
    }

    intel = get_recovery_intelligence(sample_tx, strategy_mode="CONSERVATIVE", policy=policy)
    raw_dec = intel["raw_decision"]
    final_arm = intel["recommendation"]["retry_delay"]

    strategy_decision = {
        "should_retry": intel["should_retry"],
        "recommended_delay": intel["recommendation"]["retry_delay"],
        "expected_net_value_inr": intel["expected_net_value_inr"],
    }
    exec_result = execute_retry_action(sample_tx, strategy_decision, simulator=simulator)
    # Ensure delay_executed matches final strategy arm
    assert exec_result["delay_executed"] == final_arm

    initial_pulls = policy.arm_pull_counts[final_arm]
    process_outcome_and_update(sample_tx, raw_dec, exec_result, policy=policy, audit_logger=audit_logger)
    
    assert policy.arm_pull_counts[final_arm] == initial_pulls + 1, "Policy update must increment pull count for executed strategy arm!"


def test_scale_aware_confidence_small_vs_large_amounts():
    scores_small = {
        "3d": {"score": 50.0},
        "1d": {"score": 40.0},
    }
    scores_large = {
        "3d": {"score": 5000.0},
        "1d": {"score": 4000.0},
    }

    conf_small, _ = calculate_decision_confidence(scores_small)
    conf_large, _ = calculate_decision_confidence(scores_large)

    # Relative gaps are both (50-40)/50 = 20% and (5000-4000)/5000 = 20%
    # Confidence should be equal and scale-aware!
    assert conf_small == conf_large == 0.80, "Confidence must be scale-aware and invariant under proportional scaling!"


def test_deterministic_tie_breaking():
    arm_scores = {
        "1hr": {"score": 100.0, "ucb_score": 100.0},
        "6hr": {"score": 100.0, "ucb_score": 100.0},
        "1d": {"score": 100.0, "ucb_score": 100.0},
        "3d": {"score": 100.0, "ucb_score": 100.0},
        "7d": {"score": 100.0, "ucb_score": 100.0},
    }
    tx = {"failure_code": "generic_decline"}

    best_arm, _, meta = evaluate_risk_aware_recommendation(arm_scores, "1hr", tx, strategy_mode="BALANCED")
    assert best_arm == "3d", "Deterministic tie-breaking must favor 3d among identical raw scores!"


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


def test_diagnostics_artifact_schema():
    diag_path = Path("audit/evaluation_results/phase3/phase3_mode_diagnostics.json")
    if not diag_path.exists():
        pytest.skip("Diagnostics artifact not generated yet.")

    with open(diag_path, "r", encoding="utf-8") as f:
        diag = json.load(f)

    assert "sample_size" in diag
    assert "policy_warmed" in diag
    assert diag["policy_warmed"] is True
    assert "score_gap_stats" in diag
    assert diag["score_gap_stats"]["mean"] > 0.0, "Score gap mean must be > 0 under warmed policy!"
    assert "confidence_stats" in diag
    assert "stability_distribution" in diag
    assert "mode_shift_rates" in diag
    assert "arm_distribution" in diag
    assert "first_10_transactions_detail" in diag
    assert len(diag["first_10_transactions_detail"]) == 10
