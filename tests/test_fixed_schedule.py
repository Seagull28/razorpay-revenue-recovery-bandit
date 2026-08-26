"""
test_fixed_schedule.py
Unit tests for Phase 2: Fixed-Schedule Baseline Policy and Execution Engine.
Verifies:
1. Fixed policy strictly follows 1d -> 3d -> 7d -> 7d regardless of context features.
2. Stopping rules: card_expired stops after 1 attempt; max 4 attempts enforced; stops on success.
3. Audit log schema strictly satisfies Section 7 of the Design Doc.
4. State evolution across multi-attempt sequence: simulated_day increments by delay duration,
   customer_prior_failures_this_cycle increments, day_of_month_bucket updates across boundaries.
5. Bank D drift pickup mid-sequence when a multi-attempt transaction crosses day 20.
"""

from typing import Any, Dict
import pytest

from bandit_retry_scheduler.audit.logger import AuditLogger, AuditRecord
from bandit_retry_scheduler.policies.fixed_schedule import FixedSchedulePolicy
from bandit_retry_scheduler.runner.engine import (
    PolicyExecutionEngine,
    advance_transaction_context,
)
from bandit_retry_scheduler.simulator.config import Bank, FailureCode, Network
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.ground_truth import calculate_recovery_probability


class TestFixedSchedulePolicy:
    """Tests evaluating the fixed schedule policy decision-making."""

    def test_fixed_sequence_is_context_blind(self):
        """Fixed policy must return 1d -> 3d -> 7d -> 7d regardless of failure_code, bank, or customer."""
        policy = FixedSchedulePolicy(max_attempts=4)

        contexts = [
            {"failure_code": FailureCode.ISSUER_TIMEOUT.value, "bank": Bank.BANK_A.value, "network": Network.VISA.value},
            {"failure_code": FailureCode.INSUFFICIENT_FUNDS.value, "bank": Bank.BANK_B.value, "network": Network.RUPAY.value},
            {"failure_code": FailureCode.DO_NOT_HONOR.value, "bank": Bank.BANK_D.value, "network": Network.MASTERCARD.value},
        ]

        expected_sequence = ["1d", "3d", "7d", "7d"]

        for ctx in contexts:
            for attempt_num, expected_arm in enumerate(expected_sequence, start=1):
                decision = policy.select_arm(ctx, attempt_number=attempt_num)
                assert decision.arm_chosen == expected_arm
                assert decision.expected_value is None  # Baseline does not compute expected value

    def test_stopping_rules_card_expired(self):
        """Card expired must stop after attempt 1."""
        policy = FixedSchedulePolicy(max_attempts=4)
        ctx = {"failure_code": FailureCode.CARD_EXPIRED.value}

        # Attempt 1 is allowed
        stop_1, reason_1 = policy.should_stop(ctx, attempt_number=1, previous_success=False)
        assert stop_1 is False

        # Attempt 2 must be halted
        stop_2, reason_2 = policy.should_stop(ctx, attempt_number=2, previous_success=False)
        assert stop_2 is True
        assert reason_2 == "hard_stop_card_expired"

    def test_stopping_rules_max_attempts(self):
        """No transaction should exceed max_attempts (4)."""
        policy = FixedSchedulePolicy(max_attempts=4)
        ctx = {"failure_code": FailureCode.INSUFFICIENT_FUNDS.value}

        for att in range(1, 5):
            stop, _ = policy.should_stop(ctx, attempt_number=att, previous_success=False)
            assert stop is False

        # Attempt 5 must be stopped
        stop_5, reason_5 = policy.should_stop(ctx, attempt_number=5, previous_success=False)
        assert stop_5 is True
        assert "max_attempts" in reason_5

    def test_stopping_rules_on_success(self):
        """Policy stops immediately if previous attempt succeeded."""
        policy = FixedSchedulePolicy(max_attempts=4)
        ctx = {"failure_code": FailureCode.GENERIC_DECLINE.value}

        stop, reason = policy.should_stop(ctx, attempt_number=2, previous_success=True)
        assert stop is True
        assert reason == "payment_recovered"


class TestStateEvolution:
    """Tests evaluating state updates and time progression across retry attempts."""

    def test_context_advancement_and_bucket_boundary(self):
        """
        Verify:
        - simulated_day advances by delay duration
        - customer_prior_failures_this_cycle increments (0 -> 1 -> 2+)
        - day_of_month_bucket updates correctly when crossing boundary (e.g. early -> mid)
        """
        initial_ctx = {
            "transaction_id": "tx_state_001",
            "customer_id": "cust_123",
            "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
            "bank": Bank.BANK_A.value,
            "network": Network.VISA.value,
            "amount": 5000.0,
            "simulated_day": 4,  # Day 4 is in 'early' bucket (1-5)
            "day_of_month": 4,
            "day_of_month_bucket": "early",
            "retry_attempt_number": 1,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
        }

        # Step 1: Failed attempt 1 with 1d delay
        ctx_after_1d = advance_transaction_context(initial_ctx, "1d")
        assert ctx_after_1d["simulated_day"] == 5
        assert ctx_after_1d["day_of_month"] == 5
        assert ctx_after_1d["day_of_month_bucket"] == "early"  # Day 5 is still early
        assert ctx_after_1d["retry_attempt_number"] == 2
        assert ctx_after_1d["customer_prior_failures_this_cycle"] == "1"

        # Step 2: Failed attempt 2 with 3d delay (crosses into 'mid' bucket: 5 + 3 = 8)
        ctx_after_3d = advance_transaction_context(ctx_after_1d, "3d")
        assert ctx_after_3d["simulated_day"] == 8
        assert ctx_after_3d["day_of_month"] == 8
        assert ctx_after_3d["day_of_month_bucket"] == "mid"  # Day 8 is in mid bucket (6-24)
        assert ctx_after_3d["retry_attempt_number"] == 3
        assert ctx_after_3d["customer_prior_failures_this_cycle"] == "2+"

        # Step 3: Failed attempt 3 with 7d delay (8 + 7 = 15)
        ctx_after_7d = advance_transaction_context(ctx_after_3d, "7d")
        assert ctx_after_7d["simulated_day"] == 15
        assert ctx_after_7d["day_of_month"] == 15
        assert ctx_after_7d["day_of_month_bucket"] == "mid"
        assert ctx_after_7d["retry_attempt_number"] == 4
        assert ctx_after_7d["customer_prior_failures_this_cycle"] == "2+"

    def test_bank_d_drift_picked_up_mid_sequence(self):
        """
        Verify that a multi-attempt transaction starting at day 18-19 crosses day 20
        and picks up Bank D's loosened do_not_honor recovery policy on subsequent attempts.
        """
        initial_ctx = {
            "transaction_id": "tx_drift_001",
            "customer_id": "cust_456",
            "failure_code": FailureCode.DO_NOT_HONOR.value,
            "bank": Bank.BANK_D.value,
            "network": Network.MASTERCARD.value,
            "amount": 7500.0,
            "simulated_day": 18,  # Pre-drift
            "day_of_month": 18,
            "day_of_month_bucket": "mid",
            "retry_attempt_number": 1,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
        }

        # Attempt 1 at Day 18 with 1d delay: pre-drift probability is low (~5%)
        p_attempt_1 = calculate_recovery_probability(initial_ctx, "1d")
        assert p_attempt_1 <= 0.06

        # Advance with 1d delay -> Day 19
        ctx_att2 = advance_transaction_context(initial_ctx, "1d")
        assert ctx_att2["simulated_day"] == 19
        p_attempt_2 = calculate_recovery_probability(ctx_att2, "3d")
        assert p_attempt_2 <= 0.06  # Day 19 is still pre-drift

        # Advance with 3d delay -> Day 22 (crosses day 20 drift threshold!)
        ctx_att3 = advance_transaction_context(ctx_att2, "3d")
        assert ctx_att3["simulated_day"] == 22

        # On Day 22, Bank D drift is active! For 7d delay, base drift is 0.25
        # Adjusted by cycle failure penalty (0.70x): ~ 0.25 * 0.70 = 0.175
        # For 1d delay, base drift is 0.52 * 0.70 = 0.364
        p_attempt_3_1d = calculate_recovery_probability(ctx_att3, "1d")
        p_attempt_3_7d = calculate_recovery_probability(ctx_att3, "7d")

        assert p_attempt_3_1d > 0.30
        assert p_attempt_3_7d > 0.15
        assert p_attempt_3_1d > (p_attempt_1 * 5)  # Huge jump after day 20 drift


class TestAuditLoggerAndSchema:
    """Tests evaluating Section 7 audit log schema and aggregation."""

    def test_audit_log_schema_fields(self):
        """Verify audit logger record conforms exactly to Section 7 schema."""
        logger = AuditLogger()
        ctx = {
            "failure_code": "issuer_timeout",
            "bank": "Bank A",
            "network": "Visa",
            "retry_attempt_number": 1,
            "day_of_month_bucket": "mid",
            "customer_prior_success_count": "4+",
            "customer_prior_failures_this_cycle": "0",
            "simulated_day": 3,
        }

        record = logger.log(
            transaction_id="tx_test_001",
            timestamp="day_3_att_1",
            context_vector=ctx,
            arm_chosen="1d",
            expected_value=None,
            actual_outcome=1,
            amount_recovered=2500.0,
            reward=2490.0,
        )

        assert record.transaction_id == "tx_test_001"
        assert record.timestamp == "day_3_att_1"
        assert record.context_vector == ctx
        assert record.arm_chosen == "1d"
        assert record.expected_value is None
        assert record.actual_outcome == 1
        assert record.amount_recovered == 2500.0
        assert record.reward == 2490.0

        # Flat records export check
        flat_records = logger.to_flat_records()
        assert len(flat_records) == 1
        rec = flat_records[0]
        assert "transaction_id" in rec
        assert "arm_chosen" in rec
        assert "expected_value" in rec
        assert "actual_outcome" in rec
        assert "reward" in rec
        assert "failure_code" in rec

    def test_policy_execution_engine_run(self):
        """Verify engine executes transactions and computes summary metrics."""
        sim = RetrySimulator(seed=42)
        engine = PolicyExecutionEngine(simulator=sim, retry_cost=10.0)
        policy = FixedSchedulePolicy(max_attempts=4)

        sample_txs = [
            {
                "transaction_id": "tx_001",
                "customer_id": "cust_1",
                "failure_code": FailureCode.CARD_EXPIRED.value,
                "bank": Bank.BANK_A.value,
                "network": Network.VISA.value,
                "amount": 1500.0,
                "simulated_day": 1,
                "retry_attempt_number": 1,
                "day_of_month_bucket": "early",
                "customer_prior_success_count": "1-3",
                "customer_prior_failures_this_cycle": "0",
            },
            {
                "transaction_id": "tx_002",
                "customer_id": "cust_2",
                "failure_code": FailureCode.ISSUER_TIMEOUT.value,
                "bank": Bank.BANK_C.value,
                "network": Network.VISA.value,
                "amount": 2000.0,
                "simulated_day": 1,
                "retry_attempt_number": 1,
                "day_of_month_bucket": "early",
                "customer_prior_success_count": "4+",
                "customer_prior_failures_this_cycle": "0",
            },
        ]

        logger = engine.run(sample_txs, policy)
        records = logger.to_flat_records()

        # tx_001 (card_expired) must have exactly 1 attempt recorded
        tx1_attempts = [r for r in records if r["transaction_id"] == "tx_001"]
        assert len(tx1_attempts) == 1
        assert tx1_attempts[0]["actual_outcome"] == 0

        # Summary metrics check
        metrics = logger.compute_summary_metrics()
        assert metrics["total_transactions"] == 2
        assert metrics["total_attempts"] >= 2
        assert "by_failure_code" in metrics
        assert "by_bank" in metrics
