"""
test_v2_pipeline.py
Focused unit tests for RecoverFlow V2 End-to-End Pipeline (Step 3C).
Verifies v2_context_transition, V2RetrySimulator purity, V2 ground truth, V2 eligibility gate,
V2 decision service, V2 action executor, V2 feedback loop, and V2 execution engine.
"""

import numpy as np
import pytest
from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.core.action_registry import ActionRegistry
from bandit_retry_scheduler.core.recovery_action import RecoveryAction
from bandit_retry_scheduler.core.v2_context_transition import transition_v2_context
from bandit_retry_scheduler.policies.v2_linucb import V2LinUCBPolicy
from bandit_retry_scheduler.runner.v2_engine import V2PolicyExecutionEngine
from bandit_retry_scheduler.simulator.v2_environment import V2RetrySimulator
from bandit_retry_scheduler.simulator.v2_ground_truth import calculate_v2_recovery_probability
from bandit_retry_scheduler.api.v2_eligibility import check_v2_eligibility
from bandit_retry_scheduler.api.v2_decision_service import V2DecisionService, get_v2_retry_decision
from bandit_retry_scheduler.api.v2_action_executor import execute_v2_retry_action
from bandit_retry_scheduler.api.v2_feedback_loop import process_v2_outcome_and_update


class TestV2ContextTransition:
    """Tests evaluating pure context state evolution."""

    def test_timed_retry_transition_advances_time_and_preserves_method(self):
        """Verify TIMED_RETRY advances simulated_day and preserves source_method without mutating input."""
        context = {
            "transaction_id": "tx_trans_001",
            "simulated_day": 4,
            "day_of_month": 4,
            "day_of_month_bucket": "early",
            "retry_attempt_number": 1,
            "customer_prior_failures_this_cycle": "0",
            "source_method": "card",
        }
        original_context = dict(context)

        action = RecoveryAction(
            action_id="same_method_1d",
            action_type="TIMED_RETRY",
            source_method="card",
            target_method="card",
            delay="1d",
        )
        failed_outcome = {"success": False, "reward": -10.0}

        next_ctx = transition_v2_context(context, action, failed_outcome)

        # Pure function check: original context remains untouched
        assert context == original_context

        # Evolution checks
        assert next_ctx["simulated_day"] == 5
        assert next_ctx["day_of_month"] == 5
        assert next_ctx["day_of_month_bucket"] == "early"
        assert next_ctx["retry_attempt_number"] == 2
        assert next_ctx["customer_prior_failures_this_cycle"] == "1"
        assert next_ctx["source_method"] == "card"

    def test_method_switch_transition_updates_method_and_preserves_time(self):
        """Verify METHOD_SWITCH updates source_method to target_method without advancing time."""
        context = {
            "transaction_id": "tx_trans_002",
            "simulated_day": 8,
            "day_of_month": 8,
            "day_of_month_bucket": "mid",
            "retry_attempt_number": 1,
            "customer_prior_failures_this_cycle": "0",
            "source_method": "card",
        }

        action = RecoveryAction(
            action_id="switch_to_upi",
            action_type="METHOD_SWITCH",
            source_method="card",
            target_method="upi",
            delay="0",
        )
        failed_outcome = {"success": False, "reward": -15.0}

        next_ctx = transition_v2_context(context, action, failed_outcome)

        assert next_ctx["simulated_day"] == 8
        assert next_ctx["day_of_month"] == 8
        assert next_ctx["day_of_month_bucket"] == "mid"
        assert next_ctx["retry_attempt_number"] == 2
        assert next_ctx["customer_prior_failures_this_cycle"] == "1"
        assert next_ctx["source_method"] == "upi"


class TestV2GroundTruthAndSimulator:
    """Tests evaluating synthetic V2 ground truth and simulator purity."""

    def test_card_expired_same_method_vs_method_switch_probability(self):
        """Verify card_expired on card retry gives 0.0%, while UPI switch gives synthetic >0% probability."""
        ctx = {
            "failure_code": "card_expired",
            "bank": "Bank A",
            "source_method": "card",
        }

        retry_action = RecoveryAction(
            action_id="same_method_1d",
            action_type="TIMED_RETRY",
            source_method="card",
            target_method="card",
            delay="1d",
        )
        p_retry = calculate_v2_recovery_probability(ctx, retry_action)
        assert p_retry == 0.0

        upi_switch_action = RecoveryAction(
            action_id="switch_to_upi",
            action_type="METHOD_SWITCH",
            source_method="card",
            target_method="upi",
            delay="0",
        )
        p_upi = calculate_v2_recovery_probability(ctx, upi_switch_action)
        assert p_upi > 0.30

    def test_v2_simulator_purity_and_reward_cost(self):
        """Verify V2RetrySimulator is pure (no context mutation) and enforces distinct action costs."""
        simulator = V2RetrySimulator(seed=42)
        ctx = {
            "transaction_id": "tx_sim_001",
            "failure_code": "insufficient_funds",
            "bank": "Bank B",
            "network": "Visa",
            "amount": 2000.0,
            "source_method": "card",
        }
        original_ctx = dict(ctx)

        retry_action = RecoveryAction(
            action_id="same_method_1d",
            action_type="TIMED_RETRY",
            source_method="card",
            target_method="card",
            delay="1d",
        )
        outcome_retry = simulator.simulate_action(ctx, retry_action)

        # Purity check
        assert ctx == original_ctx

        # Action cost check (10.0 INR for retry)
        assert outcome_retry["action_cost"] == 10.0
        if outcome_retry["success"]:
            assert outcome_retry["reward"] == 2000.0 - 10.0
        else:
            assert outcome_retry["reward"] == -10.0

        switch_action = RecoveryAction(
            action_id="switch_to_upi",
            action_type="METHOD_SWITCH",
            source_method="card",
            target_method="upi",
            delay="0",
        )
        outcome_switch = simulator.simulate_action(ctx, switch_action)
        assert outcome_switch["action_cost"] == 15.0


class TestV2EligibilityAndDecisionService:
    """Tests evaluating V2 eligibility gate and decision service integration."""

    def test_eligibility_card_expired_filtering(self):
        """Verify eligibility gate excludes card retries after attempt 1 for card_expired, but keeps UPI switch."""
        ctx = {
            "failure_code": "card_expired",
            "bank": "Bank C",
            "source_method": "card",
        }
        registry = ActionRegistry()
        candidates = registry.get_candidates("card")

        # Attempt 1: All candidates permitted
        is_e1, e1_cands, _ = check_v2_eligibility(ctx, candidates, attempt_number=1)
        assert is_e1 is True
        assert len(e1_cands) == 5

        # Attempt 2: Card retries filtered out, UPI/Netbanking switches remain
        is_e2, e2_cands, _ = check_v2_eligibility(ctx, candidates, attempt_number=2)
        assert is_e2 is True
        e2_ids = tuple(c.action_id for c in e2_cands)
        assert "same_method_1d" not in e2_ids
        assert "switch_to_upi" in e2_ids
        assert "switch_to_netbanking" in e2_ids

    def test_v2_decision_service_flow(self):
        """Verify V2DecisionService evaluates candidates and returns valid decision payload."""
        ctx = {
            "transaction_id": "tx_ds_001",
            "failure_code": "issuer_timeout",
            "bank": "Bank A",
            "network": "Visa",
            "source_method": "card",
        }
        registry = ActionRegistry()
        policy = V2LinUCBPolicy(registry=registry)

        decision = get_v2_retry_decision(ctx, policy=policy, registry=registry)
        assert decision["should_retry"] is True
        assert isinstance(decision["action_chosen"], RecoveryAction)
        assert decision["action_id"] == decision["action_chosen"].action_id


class TestV2EngineEndToEnd:
    """Tests evaluating V2PolicyExecutionEngine multi-attempt lifecycle execution."""

    def test_v2_engine_runs_multi_attempt_stream(self):
        """Verify engine executes transaction stream, updates policy online, and logs audit records."""
        simulator = V2RetrySimulator(seed=123)
        registry = ActionRegistry()
        policy = V2LinUCBPolicy(registry=registry)
        engine = V2PolicyExecutionEngine(simulator=simulator, registry=registry)

        transactions = [
            {
                "transaction_id": "tx_e2e_001",
                "failure_code": "insufficient_funds",
                "bank": "Bank B",
                "network": "Visa",
                "amount": 1500.0,
                "simulated_day": 1,
                "retry_attempt_number": 1,
                "day_of_month_bucket": "early",
                "customer_prior_success_count": "1-3",
                "customer_prior_failures_this_cycle": "0",
                "source_method": "card",
            },
            {
                "transaction_id": "tx_e2e_002",
                "failure_code": "card_expired",
                "bank": "Bank A",
                "network": "Mastercard",
                "amount": 2500.0,
                "simulated_day": 1,
                "retry_attempt_number": 1,
                "day_of_month_bucket": "early",
                "customer_prior_success_count": "4+",
                "customer_prior_failures_this_cycle": "0",
                "source_method": "card",
            },
        ]

        logger = engine.run(transactions, policy)
        records = logger.to_flat_records()

        assert len(records) >= 2
        tx_ids = set(r["transaction_id"] for r in records)
        assert "tx_e2e_001" in tx_ids
        assert "tx_e2e_002" in tx_ids


class TestV2EngineSourceMethodValidation:
    """Tests enforcing explicit source_method validation without silent defaults in V2 engine."""

    def test_missing_source_method_raises_value_error(self):
        """Test 1: Context without source_method must raise ValueError."""
        simulator = V2RetrySimulator(seed=42)
        registry = ActionRegistry()
        policy = V2LinUCBPolicy(registry=registry)
        engine = V2PolicyExecutionEngine(simulator=simulator, registry=registry)
        logger = AuditLogger()

        tx_missing = {
            "transaction_id": "tx_no_source",
            "failure_code": "insufficient_funds",
            "amount": 1000.0,
        }

        with pytest.raises(ValueError, match="source_method"):
            engine.process_transaction(tx_missing, policy, logger)

    def test_empty_source_method_raises_value_error(self):
        """Test 2: Context with empty string source_method must raise ValueError."""
        simulator = V2RetrySimulator(seed=42)
        registry = ActionRegistry()
        policy = V2LinUCBPolicy(registry=registry)
        engine = V2PolicyExecutionEngine(simulator=simulator, registry=registry)
        logger = AuditLogger()

        tx_empty = {
            "transaction_id": "tx_empty_source",
            "failure_code": "insufficient_funds",
            "amount": 1000.0,
            "source_method": "",
        }

        with pytest.raises(ValueError, match="source_method"):
            engine.process_transaction(tx_empty, policy, logger)

    def test_valid_card_source_method_processes_normally(self):
        """Test 3: Context with source_method='card' processes normally."""
        simulator = V2RetrySimulator(seed=42)
        registry = ActionRegistry()
        policy = V2LinUCBPolicy(registry=registry)
        engine = V2PolicyExecutionEngine(simulator=simulator, registry=registry)
        logger = AuditLogger()

        tx_card = {
            "transaction_id": "tx_card_source",
            "failure_code": "insufficient_funds",
            "amount": 1000.0,
            "source_method": "card",
        }

        engine.process_transaction(tx_card, policy, logger)
        records = logger.to_flat_records()
        assert len(records) > 0

    def test_valid_upi_source_method_processes_normally(self):
        """Test 4: Context with source_method='upi' processes normally."""
        simulator = V2RetrySimulator(seed=42)
        registry = ActionRegistry()
        policy = V2LinUCBPolicy(registry=registry)
        engine = V2PolicyExecutionEngine(simulator=simulator, registry=registry)
        logger = AuditLogger()

        tx_upi = {
            "transaction_id": "tx_upi_source",
            "failure_code": "insufficient_funds",
            "amount": 1000.0,
            "source_method": "upi",
        }

        engine.process_transaction(tx_upi, policy, logger)
        records = logger.to_flat_records()
        assert len(records) > 0

    def test_valid_netbanking_source_method_processes_normally(self):
        """Test 5: Context with source_method='netbanking' processes normally."""
        simulator = V2RetrySimulator(seed=42)
        registry = ActionRegistry()
        policy = V2LinUCBPolicy(registry=registry)
        engine = V2PolicyExecutionEngine(simulator=simulator, registry=registry)
        logger = AuditLogger()

        tx_nb = {
            "transaction_id": "tx_nb_source",
            "failure_code": "insufficient_funds",
            "amount": 1000.0,
            "source_method": "netbanking",
        }

        engine.process_transaction(tx_nb, policy, logger)
        records = logger.to_flat_records()
        assert len(records) > 0

    def test_no_mutation_or_silent_fallback_on_missing_source(self):
        """Test 6: Verify input context is not mutated and 'source_method' is not silently set to 'card'."""
        simulator = V2RetrySimulator(seed=42)
        registry = ActionRegistry()
        policy = V2LinUCBPolicy(registry=registry)
        engine = V2PolicyExecutionEngine(simulator=simulator, registry=registry)
        logger = AuditLogger()

        tx_input = {
            "transaction_id": "tx_mutation_check",
            "failure_code": "insufficient_funds",
            "amount": 500.0,
        }
        original_tx_input = dict(tx_input)

        with pytest.raises(ValueError):
            engine.process_transaction(tx_input, policy, logger)

        assert tx_input == original_tx_input
        assert "source_method" not in tx_input


class TestV2CRNPropagation:
    """Tests verifying CRN and evaluation seed propagation through V2 engine and executor."""

    def test_executor_forwards_crn_parameters_to_simulator(self):
        """Test 1: Verify execute_v2_retry_action forwards evaluation_seed, use_crn, attempt_number to simulator."""
        received_args = {}

        class DummySimulator(V2RetrySimulator):
            def simulate_action(self, context, action, attempt_number=None, evaluation_seed=None, use_crn=False):
                received_args["attempt_number"] = attempt_number
                received_args["evaluation_seed"] = evaluation_seed
                received_args["use_crn"] = use_crn
                return super().simulate_action(context, action, attempt_number, evaluation_seed, use_crn)

        sim = DummySimulator()
        tx = {"transaction_id": "tx_crn_001", "source_method": "card", "failure_code": "insufficient_funds", "amount": 100.0}
        act = RecoveryAction("same_method_1d", "TIMED_RETRY", "card", "card", "1d")
        dec = {"should_retry": True, "action_chosen": act, "action_id": act.action_id}

        execute_v2_retry_action(
            transaction=tx,
            decision=dec,
            simulator=sim,
            attempt_number=2,
            evaluation_seed=12345,
            use_crn=True,
        )

        assert received_args["attempt_number"] == 2
        assert received_args["evaluation_seed"] == 12345
        assert received_args["use_crn"] is True

    def test_engine_forwards_crn_parameters_to_executor(self):
        """Test 2: Verify V2PolicyExecutionEngine forwards evaluation_seed and use_crn through process_transaction."""
        calls = []

        class SpySimulator(V2RetrySimulator):
            def simulate_action(self, context, action, attempt_number=None, evaluation_seed=None, use_crn=False):
                calls.append({
                    "attempt_number": attempt_number,
                    "evaluation_seed": evaluation_seed,
                    "use_crn": use_crn,
                })
                return super().simulate_action(context, action, attempt_number, evaluation_seed, use_crn)

        sim = SpySimulator(seed=42)
        registry = ActionRegistry()
        policy = V2LinUCBPolicy(registry=registry)
        engine = V2PolicyExecutionEngine(simulator=sim, registry=registry)
        logger = AuditLogger()

        tx = {
            "transaction_id": "tx_engine_crn",
            "source_method": "card",
            "failure_code": "insufficient_funds",
            "amount": 100.0,
        }

        engine.process_transaction(
            initial_context=tx,
            policy=policy,
            logger=logger,
            evaluation_seed=9999,
            use_crn=True,
        )

        assert len(calls) > 0
        for call in calls:
            assert call["evaluation_seed"] == 9999
            assert call["use_crn"] is True
            assert call["attempt_number"] >= 1

    def test_crn_reproducibility(self):
        """Test 3: Verify same evaluation_seed, transaction_id, attempt_number produces identical outcome across calls."""
        sim = V2RetrySimulator()
        tx = {"transaction_id": "tx_reproducibility_001", "source_method": "card", "failure_code": "insufficient_funds", "amount": 1000.0}
        act = RecoveryAction("same_method_1d", "TIMED_RETRY", "card", "card", "1d")

        res1 = sim.simulate_action(tx, act, attempt_number=1, evaluation_seed=777, use_crn=True)
        res2 = sim.simulate_action(tx, act, attempt_number=1, evaluation_seed=777, use_crn=True)

        assert res1["success"] == res2["success"]
        assert res1["reward"] == res2["reward"]

    def test_crn_action_independence(self):
        """Test 4: Verify that the underlying CRN random draw is identical across different actions for same seed/tx/attempt."""
        from bandit_retry_scheduler.simulator.environment import get_deterministic_uniform

        seed = 55555
        tx_id = "tx_action_indep_001"
        attempt = 1

        u_expected = get_deterministic_uniform(seed, tx_id, attempt)

        sim = V2RetrySimulator()
        tx = {"transaction_id": tx_id, "source_method": "card", "failure_code": "insufficient_funds", "amount": 1000.0}
        act_card = RecoveryAction("same_method_1d", "TIMED_RETRY", "card", "card", "1d")
        act_upi = RecoveryAction("switch_to_upi", "METHOD_SWITCH", "card", "upi", "0")

        p_card = sim.get_true_recovery_probability(tx, act_card)
        p_upi = sim.get_true_recovery_probability(tx, act_upi)

        res_card = sim.simulate_action(tx, act_card, attempt_number=attempt, evaluation_seed=seed, use_crn=True)
        res_upi = sim.simulate_action(tx, act_upi, attempt_number=attempt, evaluation_seed=seed, use_crn=True)

        assert res_card["success"] == bool(u_expected < p_card)
        assert res_upi["success"] == bool(u_expected < p_upi)

    def test_non_crn_behavior_remains_valid(self):
        """Test 5: Verify use_crn=False uses standard RNG behavior without error."""
        sim = V2RetrySimulator(seed=123)
        tx = {"transaction_id": "tx_non_crn", "source_method": "card", "failure_code": "insufficient_funds", "amount": 1000.0}
        act = RecoveryAction("same_method_1d", "TIMED_RETRY", "card", "card", "1d")

        res = sim.simulate_action(tx, act, attempt_number=1, evaluation_seed=None, use_crn=False)
        assert "success" in res
        assert isinstance(res["success"], bool)


