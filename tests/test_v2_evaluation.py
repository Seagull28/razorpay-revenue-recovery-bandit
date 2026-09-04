"""
test_v2_evaluation.py
Focused unit tests for RecoverFlow V2 Evaluation Harness (run_v2_evaluation.py)
and Fix 55C-Audit Decision-Time Temporal Correctness.
"""

import json
import sys
from pathlib import Path
import pytest
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.core.action_registry import ActionRegistry
from bandit_retry_scheduler.core.recovery_action import RecoveryAction
from bandit_retry_scheduler.core.v2_ev_estimator import V2EVEstimator
from bandit_retry_scheduler.policies.v2_linucb import V2LinUCBPolicy
from bandit_retry_scheduler.run_v2_evaluation import (
    V2StaticBaselinePolicy,
    compute_v2_diagnostics,
    compute_v2_ev_feasibility_analysis,
    compute_v2_run_metrics,
    generate_v2_stream,
    run_v2_evaluation,
)
from compare_ev_impact import DecisionTimeAuditEngine, run_experiment


class TestV2EvaluationHarness:
    """Tests evaluating V2 evaluation harness, baseline validity, Fix 55A diagnostics, and Fix 55B EV Feasibility Analysis."""

    def test_1_preferred_action_eligible(self):
        """Test 1: Verify static baseline selects preferred action when it is in eligible candidates."""
        policy = V2StaticBaselinePolicy("same_method_1d", "delay", "1d")

        act_1d = RecoveryAction("same_method_1d", "TIMED_RETRY", "card", "card", "1d")
        act_3d = RecoveryAction("same_method_3d", "TIMED_RETRY", "card", "card", "3d")
        candidates = (act_1d, act_3d)

        dec = policy.select_action({"failure_code": "insufficient_funds"}, candidates, attempt_number=1)

        assert dec.action_chosen == act_1d
        assert dec.action_id == "same_method_1d"
        assert policy.target_available_count == 1
        assert policy.target_unavailable_count == 0

    def test_2_preferred_action_unavailable_returns_no_action(self):
        """Test 2: Verify static baseline returns action_chosen=None (no action) when preferred action is ineligible."""
        policy = V2StaticBaselinePolicy("same_method_1d", "delay", "1d")

        upi_switch = RecoveryAction("switch_to_upi", "METHOD_SWITCH", "card", "upi", "0")
        nb_switch = RecoveryAction("switch_to_netbanking", "METHOD_SWITCH", "card", "netbanking", "0")
        candidates = (upi_switch, nb_switch)

        dec = policy.select_action({"failure_code": "card_expired"}, candidates, attempt_number=2)

        assert dec.action_chosen is None
        assert dec.action_id == "NONE"
        assert policy.target_available_count == 0
        assert policy.target_unavailable_count == 1

    def test_3_switch_baseline_eligibility(self):
        """Test 3: Verify switch_to_upi selects UPI switch when eligible, and returns None when ineligible."""
        policy = V2StaticBaselinePolicy("switch_to_upi", "target_method", "upi")

        upi_switch = RecoveryAction("switch_to_upi", "METHOD_SWITCH", "card", "upi", "0")
        act_1d = RecoveryAction("same_method_1d", "TIMED_RETRY", "card", "card", "1d")

        dec_eligible = policy.select_action({"source_method": "card"}, (act_1d, upi_switch), attempt_number=1)
        assert dec_eligible.action_chosen == upi_switch

        upi_1d = RecoveryAction("upi_same_method_1d", "TIMED_RETRY", "upi", "upi", "1d")
        dec_ineligible = policy.select_action({"source_method": "upi"}, (upi_1d,), attempt_number=1)
        assert dec_ineligible.action_chosen is None
        assert dec_ineligible.action_id == "NONE"

    def test_4_applicability_metrics(self):
        """Test 4: Verify target action availability metrics are calculated accurately."""
        policy = V2StaticBaselinePolicy("same_method_1d", "delay", "1d")
        act_1d = RecoveryAction("same_method_1d", "TIMED_RETRY", "card", "card", "1d")
        act_3d = RecoveryAction("same_method_3d", "TIMED_RETRY", "card", "card", "3d")

        policy.select_action({}, (act_1d, act_3d))
        policy.select_action({}, (act_1d, act_3d))
        policy.select_action({}, (act_3d,))

        logger = AuditLogger()
        registry = ActionRegistry()
        metrics = compute_v2_run_metrics(logger, stream_size=3, registry=registry, baseline_policy=policy)

        assert metrics["target_action_available_count"] == 2
        assert metrics["target_action_unavailable_count"] == 1
        assert metrics["target_action_available_pct"] == 66.67

    def test_5_deterministic_evaluation(self, tmp_path):
        """Test 5: Verify running evaluation twice with identical seeds produces identical metrics and JSON output."""
        out1 = tmp_path / "res1.json"
        out2 = tmp_path / "res2.json"

        res1 = run_v2_evaluation(seeds=[42, 123], num_days=2, tx_per_day=10, output_path=str(out1))
        res2 = run_v2_evaluation(seeds=[42, 123], num_days=2, tx_per_day=10, output_path=str(out2))

        assert res1["summary"] == res2["summary"]
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_6_artifact_generation(self, tmp_path):
        """Test 6: Verify JSON output artifact contains all expected top-level sections."""
        out_file = tmp_path / "v2_eval_test.json"
        res = run_v2_evaluation(seeds=[42], num_days=1, tx_per_day=5, output_path=str(out_file))

        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))

        assert "evaluation_config" in data
        assert "summary" in data
        assert "per_seed_results" in data
        assert data["evaluation_config"]["use_crn"] is True
        assert "v2_linucb" in data["summary"]
        assert "diagnostics" in data["summary"]
        assert "ev_feasibility" in data["summary"]
        assert "baselines" in data["summary"]
        assert "comparisons" in data["summary"]

    def test_7_diagnostics_calculation(self):
        """Test 7: Verify compute_v2_diagnostics computes attempt, action, negative-reward, and cold-start metrics."""
        logger = AuditLogger()
        registry = ActionRegistry()

        logger.log("tx1", 1, {"retry_attempt_number": 1}, "same_method_1d", 0.0, 0, 0.0, -10.0)
        logger.log("tx1", 1, {"retry_attempt_number": 2}, "switch_to_upi", 0.0, 1, 1000.0, 985.0)
        logger.log("tx2", 1, {"retry_attempt_number": 1}, "same_method_3d", 0.0, 0, 0.0, -10.0)

        diag = compute_v2_diagnostics(logger, stream_size=2, registry=registry)

        assert diag["retry_intensity"]["avg_attempts_per_tx"] == 1.5
        assert diag["low_value_retry_diagnosis"]["negative_reward_retry_count"] == 2
        assert diag["low_value_retry_diagnosis"]["negative_reward_retry_pct"] == 66.67
        assert diag["low_value_retry_diagnosis"]["total_negative_reward_inr"] == -20.0

    def test_8_ucb_decomposition_and_ev_feasibility(self):
        """Test 8: Verify UCB = estimated_reward + exploration_bonus decomposition and EV feasibility analysis."""
        logger = AuditLogger()
        registry = ActionRegistry()
        policy = V2LinUCBPolicy(registry=registry, alpha=1.5)

        tx = {
            "transaction_id": "tx_ev_test",
            "failure_code": "insufficient_funds",
            "amount": 2000.0,
            "source_method": "card",
            "retry_attempt_number": 1,
        }
        logger.log("tx_ev_test", 1, tx, "same_method_1d", 0.0, 1, 2000.0, 1990.0)

        ev_analysis = compute_v2_ev_feasibility_analysis(logger, [tx], registry, policy)

        # UCB decomposition check: UCB == estimated_reward + bonus
        decomp = ev_analysis["ucb_decomposition"]
        est_reward = decomp["mean_estimated_reward_inr"]
        bonus = decomp["mean_exploration_bonus_inr"]
        ucb = decomp["mean_ucb_score_inr"]
        assert abs(ucb - (est_reward + bonus)) < 1e-4

        # Recommendation check
        assert ev_analysis["architectural_recommendation"] == "OPTION B — A separate calibrated EV estimator is required"

    # --- FIX 55C-AUDIT TEMPORAL CORRECTNESS REGRESSION TESTS ---

    def test_9_decision_time_prediction_captured(self):
        """Test 9: Verify recorded prediction is captured at decision time, BEFORE feedback update."""
        registry = ActionRegistry()
        policy = V2LinUCBPolicy(registry=registry)
        ev_estimator = V2EVEstimator(registry=registry)
        policy.ev_estimator = ev_estimator

        engine = DecisionTimeAuditEngine(registry=registry)
        engine.decision_service.policy = policy
        engine.decision_service.ev_estimator = ev_estimator

        logger = AuditLogger()
        tx = {
            "transaction_id": "tx_dt_001",
            "amount": 1000.0,
            "source_method": "card",
            "failure_code": "insufficient_funds",
            "simulated_day": 1,
        }

        # Run single transaction through engine
        engine.run([tx], policy, logger=logger, evaluation_seed=42, use_crn=True)

        assert len(engine.decision_snapshots) >= 1
        first_snap = engine.decision_snapshots[0]

        # Cold-start prediction captured at decision time must equal 0.35
        assert first_snap["chosen_action_p_hat"] == 0.35

    def test_10_prediction_does_not_mutate_estimator(self):
        """Test 10: Verify capturing decision-time predictions does not alter estimator weights."""
        registry = ActionRegistry()
        ev_estimator = V2EVEstimator(registry=registry, prior_probability=0.35)
        ctx = {"transaction_id": "tx_dt_002", "amount": 1000.0, "source_method": "card"}

        w_before = np.copy(ev_estimator.weights["same_method_1d"])
        p_before = ev_estimator.predict_probability(ctx, "same_method_1d")

        # Query probability and EV multiple times
        _ = ev_estimator.predict_probability(ctx, "same_method_1d")
        _ = ev_estimator.calculate_action_ev(ctx, registry.get_action("same_method_1d"))

        w_after = np.copy(ev_estimator.weights["same_method_1d"])
        p_after = ev_estimator.predict_probability(ctx, "same_method_1d")

        assert p_before == p_after
        assert np.array_equal(w_before, w_after)

    def test_11_temporal_ordering(self):
        """Test 11: Verify decision-time snapshot records prediction before outcome is observed."""
        res = run_experiment([42], enable_ev=True)
        snapshots = res["snapshots"]

        assert len(snapshots) > 0
        for snap in snapshots:
            if snap.get("executed"):
                # Snapshot must contain decision_time_probs captured before execution
                assert "decision_time_probs" in snap
                assert "chosen_action_p_hat" in snap
                assert "actual_outcome" in snap
                assert snap["chosen_action_id"] in snap["decision_time_probs"]

    def test_12_crn_reproducibility(self):
        """Test 12: Verify running simulation twice with identical seed under CRN yields identical snapshots."""
        res1 = run_experiment([42], enable_ev=True)
        res2 = run_experiment([42], enable_ev=True)

        snaps1 = res1["snapshots"]
        snaps2 = res2["snapshots"]

        assert len(snaps1) == len(snaps2)
        for s1, s2 in zip(snaps1, snaps2):
            assert s1["transaction_id"] == s2["transaction_id"]
            assert s1["decision_time_max_ev"] == s2["decision_time_max_ev"]
            assert s1.get("chosen_action_id") == s2.get("chosen_action_id")
            assert s1.get("actual_outcome") == s2.get("actual_outcome")

    def test_13_decision_time_ev_formula(self):
        """Test 13: Verify decision_time_EV = p_hat * amount - cost holds for all captured decision-time records."""
        res = run_experiment([42], enable_ev=True)
        snapshots = res["snapshots"]

        for snap in snapshots:
            amount = snap["amount"]
            for act_id, p_hat in snap["decision_time_probs"].items():
                ev_calc = snap["decision_time_evs"][act_id]
                cost = 15.0 if "switch" in act_id else 10.0
                expected_ev = p_hat * amount - cost
                assert abs(ev_calc - expected_ev) < 1e-2

    def test_14_no_final_model_recomputation(self):
        """Test 14: Verify decision-time predictions differ from post-hoc final estimator predictions after learning."""
        registry = ActionRegistry()
        policy = V2LinUCBPolicy(registry=registry)
        ev_estimator = V2EVEstimator(registry=registry, learning_rate=0.1)
        policy.ev_estimator = ev_estimator

        engine = DecisionTimeAuditEngine(registry=registry)
        engine.decision_service.policy = policy
        engine.decision_service.ev_estimator = ev_estimator

        stream = generate_v2_stream(seed=42, num_days=10, tx_per_day=50)
        logger = AuditLogger()
        engine.run([dict(tx) for tx in stream], policy, logger=logger, evaluation_seed=42, use_crn=True)

        # First snapshot decision-time prediction was 0.35 (cold start)
        first_snap_p_dt = engine.decision_snapshots[0]["chosen_action_p_hat"]

        # Final estimator prediction for the same initial context using trained final weights
        first_tx = stream[0]
        act_id = engine.decision_snapshots[0]["chosen_action_id"]
        final_p_post_hoc = ev_estimator.predict_probability(first_tx, act_id)

        assert first_snap_p_dt == 0.35
        # Learning has occurred, so post-hoc final prediction is different from decision-time prediction
        assert first_snap_p_dt != final_p_post_hoc
