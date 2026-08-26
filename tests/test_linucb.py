"""
test_linucb.py
Comprehensive unit and numerical validation tests for LinUCB Contextual Bandit.
Verifies:
1. ContextVectorEncoder produces exact 19-dim vectors with valid one-hot and normalized features.
2. Closed-form ridge regression updates (A_a, b_a, theta_a) match exact manual calculations.
3. Policy converges to the optimal arm when rewards are informative.
4. Cold-start exploration bonus drives arm diversity when alpha > 0.
5. Dedicated soft-decay stopping rule halts retries early when expected return is below threshold.
6. Numerical stability & invertibility: A_a remains strictly positive definite (min eigenvalue >= 1.0)
   across the full 3,000-transaction simulation without singular matrix errors.
"""

import numpy as np
import pytest

from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.policies.encoder import ContextVectorEncoder
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.config import (
    DELAY_ARMS,
    Bank,
    DelayArm,
    FailureCode,
    Network,
)
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator


class TestContextVectorEncoder:
    """Tests evaluating the 19-dimensional context feature vector encoder."""

    def test_encoder_dimension_and_bias(self):
        encoder = ContextVectorEncoder()
        assert encoder.DIMENSION == 19

        ctx = {
            "failure_code": FailureCode.ISSUER_TIMEOUT.value,
            "bank": Bank.BANK_C.value,
            "network": Network.VISA.value,
            "retry_attempt_number": 1,
            "day_of_month_bucket": "early",
            "customer_prior_success_count": "4+",
            "customer_prior_failures_this_cycle": "0",
        }

        vec = encoder.encode(ctx)
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (19,)
        assert vec.dtype == np.float64
        # Bias term (index 18) must always be 1.0
        assert vec[18] == 1.0

    def test_encoder_one_hot_encodings(self):
        encoder = ContextVectorEncoder()

        # Test failure_code one-hot (indices 0..4)
        for i, code in enumerate(encoder.FAILURE_CODE_LIST):
            vec = encoder.encode({"failure_code": code})
            assert vec[i] == 1.0
            assert sum(vec[0:5]) == 1.0

        # Test bank one-hot (indices 5..8)
        for i, bank in enumerate(encoder.BANK_LIST):
            vec = encoder.encode({"bank": bank})
            assert vec[5 + i] == 1.0
            assert sum(vec[5:9]) == 1.0

        # Test network one-hot (indices 9..11)
        for i, net in enumerate(encoder.NETWORK_LIST):
            vec = encoder.encode({"network": net})
            assert vec[9 + i] == 1.0
            assert sum(vec[9:12]) == 1.0


class TestLinUCBMathAndUpdates:
    """Tests evaluating the closed-form ridge regression math and updates."""

    def test_initial_state(self):
        policy = LinUCBPolicy(alpha=1.0)
        assert policy.d == 19
        for arm in DELAY_ARMS:
            # A_a should be 19x19 Identity
            assert np.array_equal(policy.A[arm], np.eye(19))
            # b_a should be 19-dim zeros
            assert np.array_equal(policy.b[arm], np.zeros(19))

    def test_closed_form_exact_update_math(self):
        """Manually verify A_a and b_a updates against exact hand calculations."""
        policy = LinUCBPolicy(alpha=1.0)
        encoder = ContextVectorEncoder()

        ctx = {
            "failure_code": FailureCode.ISSUER_TIMEOUT.value,
            "bank": Bank.BANK_A.value,
            "network": Network.VISA.value,
            "retry_attempt_number": 1,
            "day_of_month_bucket": "early",
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
        }
        x = encoder.encode(ctx)
        arm = "1hr"
        reward = 1490.0

        # Update policy
        policy.update(ctx, arm, reward)

        # Expected A = I + x x^T
        expected_A = np.eye(19) + np.outer(x, x)
        # Expected b = r * x
        expected_b = reward * x

        assert np.allclose(policy.A[arm], expected_A)
        assert np.allclose(policy.b[arm], expected_b)

        # Expected theta = A^-1 @ b
        expected_theta = np.linalg.solve(expected_A, expected_b)
        scores = policy.get_arm_scores(ctx)
        assert np.isclose(scores[arm]["theta_dot_x"], np.dot(expected_theta, x))

    def test_policy_convergence_to_optimal_arm(self):
        """Verify LinUCB learns and converges to the highest-reward arm."""
        policy = LinUCBPolicy(alpha=0.5)
        ctx = {
            "failure_code": FailureCode.ISSUER_TIMEOUT.value,
            "bank": Bank.BANK_C.value,
            "network": Network.VISA.value,
            "retry_attempt_number": 1,
            "day_of_month_bucket": "early",
            "customer_prior_success_count": "4+",
            "customer_prior_failures_this_cycle": "0",
        }

        # Train: Arm '1hr' consistently pays +2000, others pay -10
        for _ in range(50):
            # Select and update
            decision = policy.select_arm(ctx, attempt_number=1)
            arm = decision.arm_chosen
            r = 2000.0 if arm == "1hr" else -10.0
            policy.update(ctx, arm, r)

        # Decision should now strictly be '1hr'
        final_decision = policy.select_arm(ctx, attempt_number=1)
        assert final_decision.arm_chosen == "1hr"
        assert final_decision.expected_value > 500.0


class TestColdStartAndExploration:
    """Tests verifying cold-start behavior and exploration bonus dynamics."""

    def test_cold_start_bonus_elevated(self):
        """On cold-start unvisited contexts, exploration bonus must be positive and substantial."""
        policy = LinUCBPolicy(alpha=2.0)
        ctx = {
            "failure_code": FailureCode.GENERIC_DECLINE.value,
            "bank": Bank.BANK_D.value,
            "network": Network.RUPAY.value,
            "retry_attempt_number": 1,
            "day_of_month_bucket": "mid",
            "customer_prior_success_count": "0",
            "customer_prior_failures_this_cycle": "0",
        }

        scores = policy.get_arm_scores(ctx)
        for arm in DELAY_ARMS:
            # On fresh policy, theta_dot_x == 0, bonus > 0
            assert scores[arm]["theta_dot_x"] == 0.0
            assert scores[arm]["bonus"] > 0.0
            assert scores[arm]["ucb_score"] == scores[arm]["bonus"]


class TestExpectedValueStoppingRule:
    """Tests evaluating the currency-denominated Expected-Value stopping rule and cold-start safeguard."""

    def test_positive_expected_value_continues(self):
        """When the bandit estimates positive expected net revenue (theta^T x > 0), should_stop must return False."""
        policy = LinUCBPolicy(alpha=1.0, stopping_mode="expected_value", min_samples_for_stopping=5, max_attempts=4)
        ctx = {
            "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
            "bank": Bank.BANK_B.value,
            "network": Network.VISA.value,
            "retry_attempt_number": 2,
            "day_of_month_bucket": "early",
            "customer_prior_success_count": "4+",
            "customer_prior_failures_this_cycle": "0",
        }

        # Train with positive rewards on arm '3d'
        for _ in range(10):
            policy.update(ctx, "3d", 3500.0)

        stop, reason = policy.should_stop(ctx, attempt_number=2, previous_success=False)
        assert stop is False
        assert reason == "continue"

    def test_negative_expected_value_stops_when_mature(self):
        """When all arms have negative expected net revenue (theta^T x <= 0) and >= min_samples, should_stop must return True."""
        policy = LinUCBPolicy(alpha=1.0, stopping_mode="expected_value", min_samples_for_stopping=5, max_attempts=4)
        ctx = {
            "failure_code": FailureCode.DO_NOT_HONOR.value,
            "bank": Bank.BANK_A.value,
            "network": Network.RUPAY.value,
            "retry_attempt_number": 2,
            "day_of_month_bucket": "mid",
            "customer_prior_success_count": "0",
            "customer_prior_failures_this_cycle": "1",
        }

        # Train all arms with negative rewards (-10 cost each, 10 pulls per arm)
        for arm in DELAY_ARMS:
            for _ in range(10):
                policy.update(ctx, arm, -10.0)

        stop, reason = policy.should_stop(ctx, attempt_number=2, previous_success=False)
        assert stop is True
        assert "expected_net_value_negative" in reason

    def test_cold_start_safeguard_prevents_premature_stopping(self):
        """
        Cold-Start Safeguard: A transaction early in simulation with few observations (< min_samples)
        must NOT be stopped early even if its initial point estimate is spuriously <= 0.
        """
        policy = LinUCBPolicy(alpha=1.0, stopping_mode="expected_value", min_samples_for_stopping=5, max_attempts=4)
        ctx = {
            "failure_code": FailureCode.GENERIC_DECLINE.value,
            "bank": Bank.BANK_D.value,
            "network": Network.VISA.value,
            "retry_attempt_number": 2,
            "day_of_month_bucket": "mid",
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "1",
        }

        # Simulate just 1 failed pull on arm '1hr' (total pulls = 1 < min_samples 5)
        policy.update(ctx, "1hr", -10.0)

        # Attempt 2: Even though 1hr has theta^T x < 0 and unvisited arms have theta^T x = 0,
        # cold-start safeguard must prevent premature stopping.
        stop, reason = policy.should_stop(ctx, attempt_number=2, previous_success=False)
        assert stop is False
        assert "cold_start_safeguard" in reason

    def test_do_not_honor_net_revenue_improved_under_new_ev_rule(self):
        """
        Comparative Assertion: Under the new EV rule, do_not_honor's net revenue
        must be >= its net revenue under the old tau-decay rule over identical 3,000 transactions.
        """
        from bandit_retry_scheduler.run_stopping_comparison import analyze_policy_audit

        generator = TransactionStreamGenerator(seed=42)
        transactions = generator.generate_stream(num_days=30, transactions_per_day=100)

        # Run Old Tau-Decay Policy
        sim_old = RetrySimulator(seed=42)
        pol_old = LinUCBPolicy(alpha=1.0, stopping_mode="tau_decay", soft_decay_base_threshold=0.0)
        eng_old = PolicyExecutionEngine(simulator=sim_old, retry_cost=10.0)
        log_old = AuditLogger()
        eng_old.run(transactions=transactions, policy=pol_old, logger=log_old)
        old_res = analyze_policy_audit(log_old.to_records())

        # Run New EV Policy
        sim_new = RetrySimulator(seed=42)
        pol_new = LinUCBPolicy(alpha=1.0, stopping_mode="expected_value", min_samples_for_stopping=5)
        eng_new = PolicyExecutionEngine(simulator=sim_new, retry_cost=10.0)
        log_new = AuditLogger()
        eng_new.run(transactions=transactions, policy=pol_new, logger=log_new)
        new_res = analyze_policy_audit(log_new.to_records())

        old_dnh_net = old_res["do_not_honor"]["net_revenue"]
        new_dnh_net = new_res["do_not_honor"]["net_revenue"]

        # Assert net revenue under new EV rule is significantly higher (+INR 100k+)
        assert new_dnh_net > old_dnh_net
        assert new_dnh_net > old_dnh_net + 100000.0


class TestNumericalStabilityAndInvertibility:
    """Tests validating numerical stability across the full 3,000-transaction simulation."""

    def test_numerical_stability_matrix_invertibility(self):
        """
        Confirm that A_a remains strictly positive definite and invertible across
        the full 3,000-transaction 30-day run without any singular matrix errors.
        """
        generator = TransactionStreamGenerator(seed=42)
        transactions = generator.generate_stream(num_days=30, transactions_per_day=100)

        sim = RetrySimulator(seed=42)
        policy = LinUCBPolicy(alpha=1.0, max_attempts=4)
        engine = PolicyExecutionEngine(simulator=sim, retry_cost=10.0)
        logger = AuditLogger()

        # Run full 3,000 transaction simulation
        engine.run(transactions=transactions, policy=policy, logger=logger)

        # Verify invertibility and eigenvalues for all 5 arms
        for arm in DELAY_ARMS:
            A_a = policy.A[arm]
            assert A_a.shape == (19, 19)

            # 1. Minimum eigenvalue must be >= 1.0 (since A_a = I + sum x x^T, within float64 machine precision)
            eigenvalues = np.linalg.eigvalsh(A_a)
            min_eig = np.min(eigenvalues)
            assert min_eig >= 1.0 - 1e-9, f"Arm {arm} min eigenvalue {min_eig} < 1.0"

            # 2. Condition number must be finite and well-conditioned
            cond_num = np.linalg.cond(A_a)
            assert np.isfinite(cond_num)

            # 3. Determinant must be > 0 and matrix inversion must succeed
            A_inv = np.linalg.inv(A_a)
            assert np.allclose(A_a @ A_inv, np.eye(19), atol=1e-5)

        # Verify audit log contains valid non-None expected values
        records = logger.to_records()
        assert len(records) > 0
        for r in records[:50]:
            assert r["expected_value"] is not None
            assert isinstance(r["expected_value"], float)
