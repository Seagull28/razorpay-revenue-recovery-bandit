"""
test_v2_ev_estimator.py
Unit tests for V2 Economic Expected-Value (EV) Estimator and Safe Stopping Layer.
"""

import sys
from pathlib import Path
import pytest
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bandit_retry_scheduler.core.action_registry import ActionRegistry
from bandit_retry_scheduler.core.recovery_action import RecoveryAction
from bandit_retry_scheduler.core.v2_ev_estimator import V2EVEstimator
from bandit_retry_scheduler.api.v2_decision_service import V2DecisionService
from bandit_retry_scheduler.policies.v2_linucb import V2LinUCBPolicy
from bandit_retry_scheduler.simulator.config import FailureCode


@pytest.fixture
def registry():
    return ActionRegistry()


@pytest.fixture
def base_context():
    return {
        "transaction_id": "tx_test_001",
        "amount": 1000.0,
        "source_method": "card",
        "card_expiry_status": "VALID",
        "card_network": "VISA",
        "decline_code": "INSUFFICIENT_FUNDS",
        "simulated_day": 1,
    }


def test_cold_start_prior(registry, base_context):
    """1. Verifies p_hat == 0.35 for all unobserved actions on initialization."""
    estimator = V2EVEstimator(registry=registry, prior_probability=0.35)
    for act in registry.get_all_actions():
        p_hat = estimator.predict_probability(base_context, act.action_id)
        assert pytest.approx(p_hat, abs=1e-3) == 0.35


def test_ev_formula(registry, base_context):
    """2. Verifies EV(a|x) = p_hat * amount - cost."""
    estimator = V2EVEstimator(registry=registry, prior_probability=0.35)
    timed_act = registry.get_action("same_method_1d")
    switch_act = registry.get_action("switch_to_upi")

    # Amount = 1000, p_hat = 0.35 -> p_hat * 1000 = 350
    # Cost for timed = 10 -> EV = 340
    # Cost for switch = 15 -> EV = 335
    ev_timed = estimator.calculate_action_ev(base_context, timed_act)
    ev_switch = estimator.calculate_action_ev(base_context, switch_act)

    assert pytest.approx(ev_timed, abs=1e-2) == 340.0
    assert pytest.approx(ev_switch, abs=1e-2) == 335.0


def test_method_switch_cost(registry, base_context):
    """3. Verifies cost is 15 INR for method switch and 10 INR for timed retry."""
    estimator = V2EVEstimator(registry=registry, prior_probability=0.35)
    timed_act = registry.get_action("same_method_3d")
    switch_act = registry.get_action("switch_to_netbanking")

    ev_timed = estimator.calculate_action_ev(base_context, timed_act)
    ev_switch = estimator.calculate_action_ev(base_context, switch_act)

    # Cost difference must be exactly 5 INR
    assert pytest.approx(ev_timed - ev_switch, abs=1e-2) == 5.0


def test_non_positive_ev_stopping(registry, base_context):
    """4. Verifies should_retry = False and stop_reason = 'non_positive_expected_value' when max EV <= 0."""
    estimator = V2EVEstimator(registry=registry, prior_probability=0.001)  # tiny prior so p_hat * 10 - cost <= 0
    small_context = dict(base_context)
    small_context["amount"] = 10.0  # 0.001 * 10 - 10 = -9.99 INR

    service = V2DecisionService(registry=registry, ev_estimator=estimator)
    decision = service.get_v2_retry_decision(small_context)

    assert decision["should_retry"] is False
    assert decision["action_chosen"] is None
    assert decision["action_id"] is None
    assert decision["stop_reason"] == "non_positive_expected_value"
    assert decision["expected_net_value_inr"] <= 0.0


def test_positive_ev_continuation(registry, base_context):
    """5. Verifies decision service proceeds to policy action selection when max EV > 0."""
    estimator = V2EVEstimator(registry=registry, prior_probability=0.35)
    service = V2DecisionService(registry=registry, ev_estimator=estimator)
    decision = service.get_v2_retry_decision(base_context)

    assert decision["should_retry"] is True
    assert decision["action_chosen"] is not None
    assert decision["action_id"] is not None
    assert decision["stop_reason"] is None


def test_linucb_selector_preservation(registry, base_context):
    """6. Verifies LinUCB policy selects action when max EV > 0 (EV estimator does NOT override LinUCB)."""
    estimator = V2EVEstimator(registry=registry, prior_probability=0.35)
    policy = V2LinUCBPolicy(registry=registry)
    service = V2DecisionService(policy=policy, registry=registry, ev_estimator=estimator)

    candidates = registry.get_candidates("card")
    policy_decision = policy.select_action(base_context, candidates)
    service_decision = service.get_v2_retry_decision(base_context)

    # Action selected by LinUCB must match service decision
    assert service_decision["action_id"] == policy_decision.action_id


def test_eligibility_interaction(registry, base_context):
    """7. Verifies safety eligibility gate runs before EV estimator."""
    estimator = V2EVEstimator(registry=registry, prior_probability=0.35)
    service = V2DecisionService(registry=registry, ev_estimator=estimator)

    # attempt 5 exceeds max_attempts = 4
    decision = service.get_v2_retry_decision(base_context, attempt_number=5)

    assert decision["should_retry"] is False
    assert decision["stop_reason"] == "max_attempts_reached_4"


def test_previous_success(registry, base_context):
    """8. Verifies safety gate stops on previous_success = True before EV estimator is called."""
    estimator = V2EVEstimator(registry=registry, prior_probability=0.35)
    service = V2DecisionService(registry=registry, ev_estimator=estimator)

    decision = service.get_v2_retry_decision(base_context, previous_success=True)

    assert decision["should_retry"] is False
    assert decision["stop_reason"] == "payment_recovered"


def test_card_expired(registry, base_context):
    """9. Verifies safety gate filters card-expired transactions / actions before EV estimator."""
    estimator = V2EVEstimator(registry=registry, prior_probability=0.35)
    service = V2DecisionService(registry=registry, ev_estimator=estimator)

    expired_context = dict(base_context)
    expired_context["failure_code"] = FailureCode.CARD_EXPIRED.value

    # On attempt 2 for CARD_EXPIRED, same-method card retries are filtered out by eligibility gate
    decision = service.get_v2_retry_decision(expired_context, attempt_number=2)

    if decision["should_retry"]:
        assert decision["action_chosen"].action_type == "METHOD_SWITCH"


def test_feedback_learning(registry, base_context):
    """10. Verifies calling update(context, action_id, success) updates weights and changes predicted probability/EV."""
    estimator = V2EVEstimator(registry=registry, prior_probability=0.35, learning_rate=0.5)
    act_id = "same_method_1d"
    p_before = estimator.predict_probability(base_context, act_id)

    # Train with repeated failures
    for _ in range(20):
        estimator.update(base_context, act_id, success=False)

    p_after = estimator.predict_probability(base_context, act_id)
    assert p_after < p_before


def test_no_ground_truth_leakage():
    """11. Verifies V2EVEstimator does NOT import or use v2_ground_truth.py or simulator probabilities."""
    import inspect
    import bandit_retry_scheduler.core.v2_ev_estimator as ev_mod

    source_code = inspect.getsource(ev_mod)
    assert "v2_ground_truth" not in source_code
    assert "calculate_v2_recovery_probability" not in source_code
    assert "V2RetrySimulator" not in source_code


def test_determinism(registry, base_context):
    """12. Verifies running the same context and outcome sequence produces identical weights and EV predictions across separate estimator instances."""
    est1 = V2EVEstimator(registry=registry, prior_probability=0.35)
    est2 = V2EVEstimator(registry=registry, prior_probability=0.35)

    act_id = "same_method_1d"
    outcomes = [True, False, False, True, False]

    for out in outcomes:
        est1.update(base_context, act_id, out)
        est2.update(base_context, act_id, out)

    p1 = est1.predict_probability(base_context, act_id)
    p2 = est2.predict_probability(base_context, act_id)

    assert p1 == p2
    assert np.allclose(est1.weights[act_id], est2.weights[act_id])
