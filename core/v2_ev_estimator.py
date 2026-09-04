"""
v2_ev_estimator.py
Economic Expected-Value (EV) Estimator for RecoverFlow V2.
Maintains online calibrated per-action success probability models P_hat(success | x, a)
and computes expected net value:
    EV(a | x) = P_hat(success | x, a) * transaction_amount - action_cost(a)
Decoupled from V2 LinUCB policy and V2 simulator ground truth.
"""

from typing import Any, Dict, Optional, Sequence, Tuple
import numpy as np

from bandit_retry_scheduler.core.action_registry import ActionRegistry
from bandit_retry_scheduler.core.recovery_action import RecoveryAction
from bandit_retry_scheduler.policies.v2_encoder import V2ContextVectorEncoder
from bandit_retry_scheduler.simulator.v2_environment import V2_METHOD_SWITCH_COST, V2_TIMED_RETRY_COST


class V2EVEstimator:
    """
    Standalone Economic EV Estimator for V2 Recovery Actions.

    Maintains per-action online logistic probability models:
        P_hat(success | x, a) = sigmoid(w_a^T x)

    Uses an explicit, optimistic prior (default p_prior = 0.35) at cold-start (w_a = w_prior)
    so that initial EV is positive and retries are never halted prematurely.
    Updates w_a online via SGD upon receiving execution outcomes.
    """

    def __init__(
        self,
        registry: Optional[ActionRegistry] = None,
        learning_rate: float = 0.05,
        prior_probability: float = 0.35,
        l2_reg: float = 0.01,
    ):
        self.registry = registry if registry is not None else ActionRegistry()
        self.encoder = V2ContextVectorEncoder()
        self.d = self.encoder.DIMENSION  # 22
        self.lr = float(learning_rate)
        self.l2_reg = float(l2_reg)

        self.prior_p = float(prior_probability)
        bias_prior = float(np.log(self.prior_p / (1.0 - self.prior_p)))

        all_actions = self.registry.get_all_actions()
        self.registered_action_ids = tuple(act.action_id for act in all_actions)

        self.weights: Dict[str, np.ndarray] = {}
        for act_id in self.registered_action_ids:
            w = np.zeros(self.d, dtype=np.float64)
            w[-1] = bias_prior
            self.weights[act_id] = w

        self.observation_counts: Dict[str, int] = {act_id: 0 for act_id in self.registered_action_ids}

    def predict_probability(self, context: Dict[str, Any], action_id: str) -> float:
        """
        Predicts P_hat(success | context, action_id) using current online logistic weights.
        Returns float probability in (0, 1).
        """
        if action_id not in self.weights:
            return self.prior_p

        x = self.encoder.encode(context)
        w = self.weights[action_id]
        z = float(np.dot(w, x))
        z_clipped = np.clip(z, -20.0, 20.0)
        p_hat = 1.0 / (1.0 + np.exp(-z_clipped))
        return float(p_hat)

    def calculate_action_ev(self, context: Dict[str, Any], action: RecoveryAction) -> float:
        """
        Calculates Economic Expected Value EV(a | x) = P_hat(success | x, a) * amount - cost(a).
        """
        amount = float(context.get("amount", 1000.0))
        p_hat = self.predict_probability(context, action.action_id)
        cost = V2_METHOD_SWITCH_COST if action.action_type == "METHOD_SWITCH" else V2_TIMED_RETRY_COST
        ev = p_hat * amount - cost
        return float(ev)

    def evaluate_economic_feasibility(
        self,
        context: Dict[str, Any],
        eligible_candidates: Sequence[RecoveryAction],
    ) -> Tuple[bool, Optional[RecoveryAction], float, Dict[str, float]]:
        """
        Evaluates EV for all eligible candidate actions.

        Returns:
        --------
        (is_feasible: bool, best_action: Optional[RecoveryAction], max_ev: float, action_evs: Dict[str, float])
        """
        if not eligible_candidates:
            return False, None, 0.0, {}

        action_evs: Dict[str, float] = {}
        best_act: Optional[RecoveryAction] = None
        max_ev = -float("inf")

        for act in eligible_candidates:
            ev = self.calculate_action_ev(context, act)
            action_evs[act.action_id] = round(ev, 2)
            if ev > max_ev:
                max_ev = ev
                best_act = act

        is_feasible = bool(max_ev > 0.0)
        return is_feasible, best_act, round(float(max_ev), 2), action_evs

    def update(self, context: Dict[str, Any], action_id: str, success: bool) -> None:
        """
        Updates logistic probability weights for action_id via online SGD.
        """
        if action_id not in self.weights:
            return

        x = self.encoder.encode(context)
        p_hat = self.predict_probability(context, action_id)
        y = 1.0 if success else 0.0

        error = y - p_hat
        w = self.weights[action_id]
        grad = error * x - self.l2_reg * w
        grad[-1] += self.l2_reg * w[-1]

        self.weights[action_id] += self.lr * grad
        self.observation_counts[action_id] += 1
