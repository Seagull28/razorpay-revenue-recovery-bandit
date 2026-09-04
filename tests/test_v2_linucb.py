"""
test_v2_linucb.py
Focused unit tests for RecoverFlow V2 Policy & Action-Selection (Step 3B).
Verifies V2ContextVectorEncoder, V2LinUCBPolicy candidate scoring, strict validation,
action_id preservation, matrix updates, cold-start exploration, and V1 isolation.
"""

import numpy as np
import pytest
from bandit_retry_scheduler.core.action_registry import ActionRegistry
from bandit_retry_scheduler.core.recovery_action import RecoveryAction
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.policies.v2_encoder import V2ContextVectorEncoder
from bandit_retry_scheduler.policies.v2_linucb import V2LinUCBPolicy, V2PolicyDecision


class TestV2EncoderValidation:
    """Test suite evaluating V2ContextVectorEncoder."""

    def test_v2_encoder_dimension_and_success(self):
        """Verify encoder returns a 22-dimensional float64 vector when valid context is supplied."""
        encoder = V2ContextVectorEncoder()
        ctx = {
            "failure_code": "insufficient_funds",
            "bank": "Bank A",
            "network": "Visa",
            "day_of_month_bucket": "early",
            "retry_attempt_number": 1,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
            "source_method": "card",
        }

        vec = encoder.encode(ctx)
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (22,)
        assert vec.dtype == np.float64
        assert vec[-1] == 1.0  # Bias term

    @pytest.mark.parametrize("invalid_source", [None, "", "   ", 123, "crypto", "paypal"])
    def test_v2_encoder_missing_or_invalid_source_method(self, invalid_source):
        """Verify encoder raises ValueError when source_method is missing, empty, or invalid."""
        encoder = V2ContextVectorEncoder()
        ctx = {
            "failure_code": "issuer_timeout",
            "bank": "Bank B",
            "source_method": invalid_source,
        }

        with pytest.raises(ValueError) as exc_info:
            encoder.encode(ctx)

        assert "source_method" in str(exc_info.value)


class TestV2LinUCBPolicy:
    """Test suite evaluating V2LinUCBPolicy action selection and parameter updates."""

    @pytest.fixture
    def registry(self):
        return ActionRegistry()

    @pytest.fixture
    def policy(self, registry):
        return V2LinUCBPolicy(registry=registry, alpha=1.0)

    @pytest.fixture
    def valid_card_context(self):
        return {
            "transaction_id": "tx_v2_test_001",
            "failure_code": "insufficient_funds",
            "bank": "Bank A",
            "network": "Visa",
            "day_of_month_bucket": "early",
            "retry_attempt_number": 1,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
            "source_method": "card",
        }

    def test_policy_initialization(self, policy, registry):
        """Verify V2 policy initializes A (22x22 eye) and b (22 zero) for all 16 registered action IDs."""
        all_actions = registry.get_all_actions()
        assert len(policy.A) == 16
        assert len(policy.b) == 16

        for act in all_actions:
            act_id = act.action_id
            assert act_id in policy.A
            assert policy.A[act_id].shape == (22, 22)
            assert np.array_equal(policy.A[act_id], np.eye(22))
            assert np.array_equal(policy.b[act_id], np.zeros(22))
            assert policy.arm_pull_counts[act_id] == 0

    def test_select_action_candidate_subset_scoring(self, policy, registry, valid_card_context):
        """Verify select_action scores ONLY candidate actions and returns a valid V2PolicyDecision."""
        candidates = registry.get_candidates("card")  # 5 candidates
        decision = policy.select_action(valid_card_context, candidates)

        assert isinstance(decision, V2PolicyDecision)
        assert isinstance(decision.action_chosen, RecoveryAction)
        assert decision.action_id == decision.action_chosen.action_id
        assert decision.action_id in tuple(c.action_id for c in candidates)
        assert "switch_to_card" not in decision.metadata["action_scores"]

    def test_missing_source_method_raises_value_error(self, policy, registry):
        """Verify select_action raises ValueError when source_method is missing from context."""
        ctx_missing_source = {
            "failure_code": "issuer_timeout",
            "bank": "Bank B",
        }
        candidates = registry.get_candidates("card")

        with pytest.raises(ValueError) as exc_info:
            policy.select_action(ctx_missing_source, candidates)

        assert "source_method" in str(exc_info.value)

    def test_empty_candidates_raises_value_error(self, policy, valid_card_context):
        """Verify select_action raises ValueError when candidate tuple is empty."""
        with pytest.raises(ValueError) as exc_info:
            policy.select_action(valid_card_context, ())

        assert "No candidate actions" in str(exc_info.value)

    def test_invalid_candidate_type_raises_type_error(self, policy, valid_card_context):
        """Verify select_action raises TypeError when candidates contains non-RecoveryAction items."""
        invalid_candidates = ["same_method_1d", "switch_to_upi"]

        with pytest.raises(TypeError) as exc_info:
            policy.select_action(valid_card_context, invalid_candidates)

        assert "RecoveryAction" in str(exc_info.value)

    def test_unregistered_candidate_action_id_raises_key_error(self, policy, valid_card_context):
        """Verify select_action raises KeyError when a candidate action_id is not registered in policy state."""
        unregistered_action = RecoveryAction(
            action_id="unregistered_crypto_action",
            action_type="METHOD_SWITCH",
            source_method="card",
            target_method="crypto",
            delay="0",
        )

        with pytest.raises(KeyError) as exc_info:
            policy.select_action(valid_card_context, (unregistered_action,))

        assert "unregistered_crypto_action" in str(exc_info.value)

    def test_policy_update(self, policy, valid_card_context):
        """Verify update modifies matrix state and pull count for the specified action_id only."""
        action_id = "same_method_1d"
        initial_A = policy.A[action_id].copy()
        initial_b = policy.b[action_id].copy()

        policy.update(valid_card_context, action_id=action_id, reward=1490.0)

        assert not np.array_equal(policy.A[action_id], initial_A)
        assert not np.array_equal(policy.b[action_id], initial_b)
        assert policy.arm_pull_counts[action_id] == 1

        # Confirm other action matrices remain untouched
        other_id = "switch_to_upi"
        assert np.array_equal(policy.A[other_id], np.eye(22))
        assert policy.arm_pull_counts[other_id] == 0

    def test_update_unregistered_action_id_raises_key_error(self, policy, valid_card_context):
        """Verify update raises KeyError when passed an unknown action_id."""
        with pytest.raises(KeyError) as exc_info:
            policy.update(valid_card_context, action_id="unknown_action_99", reward=100.0)

        assert "unknown_action_99" in str(exc_info.value)

    def test_deterministic_tie_breaking(self, policy, registry, valid_card_context):
        """Verify candidate selection breaks score ties deterministically by candidate order."""
        candidates = registry.get_candidates("card")
        # Under zero pulls and alpha=1.0, all unpulled candidates have equal initial UCB scores
        decision_1 = policy.select_action(valid_card_context, candidates)
        assert decision_1.action_id == candidates[0].action_id

        # Reversed order candidates
        reversed_candidates = tuple(reversed(candidates))
        decision_2 = policy.select_action(valid_card_context, reversed_candidates)
        assert decision_2.action_id == reversed_candidates[0].action_id

    def test_v1_and_v2_policy_coexistence(self, valid_card_context):
        """Verify V1 LinUCBPolicy (d=19) and V2 V2LinUCBPolicy (d=22) coexist independently."""
        v1_policy = LinUCBPolicy()
        v2_policy = V2LinUCBPolicy()
        registry = ActionRegistry()

        # V1 decision
        v1_decision = v1_policy.select_arm(valid_card_context, attempt_number=1)
        assert v1_decision.arm_chosen in ["1hr", "6hr", "1d", "3d", "7d"]
        assert v1_policy.d == 19

        # V2 decision
        v2_candidates = registry.get_candidates("card")
        v2_decision = v2_policy.select_action(valid_card_context, v2_candidates)
        assert v2_decision.action_id in tuple(c.action_id for c in v2_candidates)
        assert v2_policy.d == 22
