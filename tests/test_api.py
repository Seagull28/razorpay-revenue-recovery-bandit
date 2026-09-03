"""
test_api.py
Unit tests for RecoverFlow API layer.
Verifies faithful delegation to existing policies, eligibility gate semantics,
explainability generation, and audit logging integration.
"""

import pytest
from bandit_retry_scheduler.api.eligibility import check_eligibility
from bandit_retry_scheduler.api.explainability import generate_decision_explanation
from bandit_retry_scheduler.api.decision_service import get_retry_decision, DecisionService
from bandit_retry_scheduler.api.audit_service import AuditService
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.simulator.config import FailureCode, Bank, Network
from bandit_retry_scheduler.audit.logger import AuditLogger


class TestEligibilityGate:
    """Tests evaluating pre-check eligibility safety gate behavior."""

    def test_card_expired_attempt_1_is_eligible(self):
        """Confirm card_expired IS eligible on attempt 1 (1 attempt permitted)."""
        tx = {
            "transaction_id": "tx_exp_1",
            "failure_code": FailureCode.CARD_EXPIRED.value,
            "bank": Bank.BANK_A.value,
        }
        eligible, reason = check_eligibility(tx, attempt_number=1)
        assert eligible is True
        assert reason == "eligible"

    def test_card_expired_attempt_2_is_ineligible(self):
        """Confirm card_expired is INELIGIBLE on attempt 2 (hard stop kicks in)."""
        tx = {
            "transaction_id": "tx_exp_2",
            "failure_code": FailureCode.CARD_EXPIRED.value,
            "bank": Bank.BANK_A.value,
        }
        eligible, reason = check_eligibility(tx, attempt_number=2)
        assert eligible is False
        assert reason == "hard_stop_card_expired"

    def test_max_attempts_exceeded_is_ineligible(self):
        """Confirm attempt_number > 4 is INELIGIBLE."""
        tx = {
            "transaction_id": "tx_max",
            "failure_code": FailureCode.ISSUER_TIMEOUT.value,
            "bank": Bank.BANK_B.value,
        }
        eligible, reason = check_eligibility(tx, attempt_number=5, max_attempts=4)
        assert eligible is False
        assert "max_attempts_reached" in reason


class TestDecisionService:
    """Tests evaluating Recovery Decision API delegation and output structure."""

    def test_get_retry_decision_arm_scores_completeness(self):
        """Confirm arm_scores field contains all 5 arms with complete score breakdown."""
        tx = {
            "transaction_id": "tx_test_5arms",
            "amount": 1500.0,
            "failure_code": FailureCode.ISSUER_TIMEOUT.value,
            "bank": Bank.BANK_C.value,
            "network": Network.VISA.value,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "mid",
        }
        policy = LinUCBPolicy()
        res = get_retry_decision(tx, policy=policy, attempt_number=1)

        assert "arm_scores" in res
        scores = res["arm_scores"]
        expected_arms = ["1hr", "6hr", "1d", "3d", "7d"]
        assert list(scores.keys()) == expected_arms

        for arm in expected_arms:
            arm_data = scores[arm]
            assert "theta_dot_x" in arm_data
            assert "bonus" in arm_data
            assert "ucb_score" in arm_data
            assert "pull_count" in arm_data

    def test_faithful_delegation_to_policy(self):
        """Confirm API decision matches direct call to underlying LinUCB policy."""
        tx = {
            "transaction_id": "tx_delegation",
            "amount": 2500.0,
            "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
            "bank": Bank.BANK_B.value,
            "network": Network.MASTERCARD.value,
            "customer_prior_success_count": "4+",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "early",
        }
        policy = LinUCBPolicy()
        
        # Direct policy call
        direct_decision = policy.select_arm(tx, attempt_number=1)
        
        # API call
        api_res = get_retry_decision(tx, policy=policy, attempt_number=1)

        assert api_res["should_retry"] is True
        assert api_res["recommended_delay"] == direct_decision.arm_chosen
        assert pytest.approx(api_res["expected_net_value_inr"], 0.01) == float(direct_decision.expected_value)

    def test_ev_stopping_rule_halt(self):
        """Confirm API returns should_retry=False when mature EV stopping rule triggers."""
        tx = {
            "transaction_id": "tx_negative_ev",
            "amount": 100.0,
            "failure_code": FailureCode.DO_NOT_HONOR.value,
            "bank": Bank.BANK_A.value,
            "network": Network.RUPAY.value,
            "customer_prior_success_count": "0",
            "customer_prior_failures_this_cycle": "2+",
            "day_of_month_bucket": "late",
        }
        policy = LinUCBPolicy(min_samples_for_stopping=15)
        # Artificially set pull counts above 15 so EV stopping rule evaluates
        for arm in policy.arms:
            policy.arm_pull_counts[arm] = 20

        api_res = get_retry_decision(tx, policy=policy, attempt_number=2)
        assert api_res["should_retry"] is False
        assert api_res["recommended_delay"] is None
        assert api_res["stop_reason"].startswith("expected_net_value_negative")


class TestExplainabilityAndAudit:
    """Tests evaluating explanation string generation and audit service integration."""

    def test_explanation_formatting_for_retry(self):
        """Confirm retry explanation includes recommended delay, amount, net value, and alternative arms."""
        tx = {
            "transaction_id": "tx_exp_fmt",
            "amount": 5000.0,
            "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
            "bank": Bank.BANK_B.value,
        }
        decision = {
            "should_retry": True,
            "recommended_delay": "3d",
            "expected_net_value_inr": 2240.0,
            "stop_reason": None,
            "arm_scores": {
                "1hr": {"theta_dot_x": 240.0, "bonus": 5.0, "ucb_score": 245.0, "pull_count": 20},
                "6hr": {"theta_dot_x": 390.0, "bonus": 5.0, "ucb_score": 395.0, "pull_count": 20},
                "1d": {"theta_dot_x": 740.0, "bonus": 5.0, "ucb_score": 745.0, "pull_count": 20},
                "3d": {"theta_dot_x": 2240.0, "bonus": 5.0, "ucb_score": 2245.0, "pull_count": 20},
                "7d": {"theta_dot_x": 1490.0, "bonus": 5.0, "ucb_score": 1495.0, "pull_count": 20},
            },
        }
        explanation = generate_decision_explanation(tx, decision)

        assert "Recommended 3d delay" in explanation
        assert "INR 5,000.00" in explanation
        assert "INR 2,240.00" in explanation
        assert "Alternative arms considered" in explanation
        assert "1hr (EV: INR 240.00)" in explanation

    def test_audit_service_retrieval(self):
        """Confirm AuditService logs decision and retrieves history by transaction_id."""
        logger = AuditLogger()
        service = DecisionService(audit_logger=logger)
        audit_svc = AuditService(audit_logger=logger)

        tx = {
            "transaction_id": "tx_audit_999",
            "amount": 1500.0,
            "failure_code": FailureCode.ISSUER_TIMEOUT.value,
            "bank": Bank.BANK_C.value,
        }
        service.get_retry_decision(tx, attempt_number=1)
        
        history = audit_svc.get_transaction_history("tx_audit_999")
        assert len(history) == 1
        assert history[0].transaction_id == "tx_audit_999"

    def test_audit_service_get_summary_success(self):
        """Confirm AuditService.get_audit_summary() executes without error and returns summary dict."""
        logger = AuditLogger()
        logger.log(
            transaction_id="tx_sum_1",
            timestamp="day_1_att_1",
            context_vector={"failure_code": "issuer_timeout", "bank": "Bank A"},
            arm_chosen="1hr",
            expected_value=500.0,
            actual_outcome=1,
            amount_recovered=1500.0,
            reward=1490.0,
        )
        audit_svc = AuditService(audit_logger=logger)
        summary = audit_svc.get_audit_summary()
        
        assert isinstance(summary, dict)
        assert summary["total_transactions"] == 1
        assert summary["total_attempts"] == 1
        assert summary["recovered_transactions"] == 1
        assert summary["total_revenue_recovered"] == 1500.0


class TestTier2ActionExecutor:
    """Tests evaluating Action Execution safety boundaries and simulator delegation."""

    def test_stopped_decision_cannot_execute(self, monkeypatch):
        """Confirm execute_retry_action strictly REJECTS execution if should_retry is False."""
        from bandit_retry_scheduler.api.action_executor import execute_retry_action
        from bandit_retry_scheduler.simulator.environment import RetrySimulator

        sim = RetrySimulator(seed=42)

        # Monkeypatch simulate_retry to fail if called unexpectedly
        def _fail_if_called(*args, **kwargs):
            pytest.fail("simulate_retry MUST NOT be called for a stopped decision!")

        monkeypatch.setattr(sim, "simulate_retry", _fail_if_called)

        tx = {"transaction_id": "tx_stopped", "failure_code": FailureCode.CARD_EXPIRED.value}
        stopped_decision = {
            "transaction_id": "tx_stopped",
            "should_retry": False,
            "recommended_delay": "1d", # even if recommended_delay is present
            "stop_reason": "hard_stop_card_expired",
        }

        exec_res = execute_retry_action(tx, stopped_decision, sim)
        assert exec_res["action_taken"] == "no_action"
        assert exec_res["delay_executed"] is None
        assert exec_res["outcome"] == "not_attempted"
        assert exec_res["amount_recovered"] == 0.0
        assert exec_res["reward"] == 0.0

    def test_retry_decision_executes_against_simulator(self):
        """Confirm eligible decision invokes simulator and returns execution record."""
        from bandit_retry_scheduler.api.action_executor import execute_retry_action
        from bandit_retry_scheduler.simulator.environment import RetrySimulator

        sim = RetrySimulator(seed=42)
        tx = {
            "transaction_id": "tx_exec_01",
            "amount": 2500.0,
            "failure_code": FailureCode.ISSUER_TIMEOUT.value,
            "bank": Bank.BANK_C.value,
        }
        eligible_decision = {
            "transaction_id": "tx_exec_01",
            "should_retry": True,
            "recommended_delay": "1hr",
        }

        exec_res = execute_retry_action(tx, eligible_decision, sim)
        assert exec_res["action_taken"] == "retry"
        assert exec_res["delay_executed"] == "1hr"
        assert exec_res["outcome"] in ["success", "failure"]


class TestTier2FeedbackLoop:
    """Tests evaluating online learning feedback loop and policy state snapshots."""

    def test_end_to_end_loop_updates_policy_state(self):
        """Confirm end-to-end API pipeline updates LinUCB A_a and b_a matrices for chosen arm."""
        import numpy as np
        from bandit_retry_scheduler.api import get_retry_decision, execute_retry_action, process_outcome_and_update
        from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
        from bandit_retry_scheduler.simulator.environment import RetrySimulator

        policy = LinUCBPolicy()
        sim = RetrySimulator(seed=101)
        tx = {
            "transaction_id": "tx_e2e_loop",
            "amount": 3000.0,
            "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
            "bank": Bank.BANK_B.value,
            "network": Network.MASTERCARD.value,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "mid",
        }

        # Step 1: Decision
        decision = get_retry_decision(tx, policy=policy, attempt_number=1)
        chosen_arm = decision["recommended_delay"]
        assert decision["should_retry"] is True

        # Take BEFORE snapshot of policy parameters for chosen_arm
        A_before = policy.A[chosen_arm].copy()
        b_before = policy.b[chosen_arm].copy()

        # Step 2: Execution
        exec_res = execute_retry_action(tx, decision, sim)

        # Step 3: Feedback loop update
        process_outcome_and_update(tx, decision, exec_res, policy)

        # Take AFTER snapshot of policy parameters for chosen_arm
        A_after = policy.A[chosen_arm]
        b_after = policy.b[chosen_arm]

        # Assert policy state matrices changed numerically
        diff_A = np.linalg.norm(A_after - A_before)
        diff_b = np.linalg.norm(b_after - b_before)

        assert diff_A > 0, "Matrix A_a MUST update after feedback loop execution!"
        assert diff_b > 0, "Vector b_a MUST update after feedback loop execution!"

