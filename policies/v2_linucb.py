"""
v2_linucb.py
Disjoint Linear Upper Confidence Bound (LinUCB) policy for RecoverFlow V2.
Operates on V2 RecoveryAction objects and stable action_ids, supporting candidate-subset scoring.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple
import numpy as np

from bandit_retry_scheduler.core.action_registry import ActionRegistry
from bandit_retry_scheduler.core.recovery_action import RecoveryAction
from bandit_retry_scheduler.policies.v2_encoder import V2ContextVectorEncoder
from bandit_retry_scheduler.simulator.config import DEFAULT_RETRY_COST


@dataclass
class V2PolicyDecision:
    """Represents a V2 action-aware policy decision."""

    action_chosen: RecoveryAction
    action_id: str
    expected_value: float
    metadata: Dict[str, Any]


class V2LinUCBPolicy:
    """
    Action-Aware Disjoint LinUCB Contextual Bandit Policy for RecoverFlow V2.

    Maintains independent ridge regression models (A_a, b_a) per registered RecoveryAction action_id.
    Scores ONLY the candidate RecoveryAction objects supplied to select_action().
    """

    def __init__(
        self,
        registry: Optional[ActionRegistry] = None,
        alpha: float = 1.0,
        max_attempts: int = 4,
        retry_cost: float = DEFAULT_RETRY_COST,
    ):
        self.registry = registry if registry is not None else ActionRegistry()
        self.alpha = float(alpha)
        self.max_attempts = int(max_attempts)
        self.retry_cost = float(retry_cost)

        self.encoder = V2ContextVectorEncoder()
        self.d = self.encoder.DIMENSION  # 22 dimensions

        self.all_actions = self.registry.get_all_actions()
        self.registered_action_ids = tuple(act.action_id for act in self.all_actions)

        # Initialize disjoint ridge regression state matrices per registered action_id
        self.A: Dict[str, np.ndarray] = {
            act_id: np.eye(self.d, dtype=np.float64) for act_id in self.registered_action_ids
        }
        self.b: Dict[str, np.ndarray] = {
            act_id: np.zeros(self.d, dtype=np.float64) for act_id in self.registered_action_ids
        }

        # Track pull counts per action_id
        self.arm_pull_counts: Dict[str, int] = {act_id: 0 for act_id in self.registered_action_ids}

        # Cache of latest decision details
        self.last_decision_details: Dict[str, Any] = {}

    def get_action_scores(
        self,
        context: Dict[str, Any],
        candidates: Sequence[RecoveryAction],
    ) -> Dict[str, Dict[str, float]]:
        """
        Computes point estimate (exploitation), exploration bonus, and combined UCB score
        for ONLY the candidate RecoveryAction objects provided.

        Raises:
        -------
        ValueError: If context is invalid or candidates sequence is empty/invalid.
        TypeError: If an item in candidates is not a RecoveryAction.
        KeyError: If a candidate's action_id is not registered in policy state.
        """
        x = self.encoder.encode(context)

        if not candidates:
            raise ValueError("No candidate actions provided for selection.")

        scores: Dict[str, Dict[str, float]] = {}

        for cand in candidates:
            if not isinstance(cand, RecoveryAction):
                raise TypeError(f"Expected RecoveryAction instance, got {type(cand)}.")

            act_id = cand.action_id
            if act_id not in self.A:
                raise KeyError(f"Action ID '{act_id}' is not registered in V2 policy state.")

            A_a = self.A[act_id]
            b_a = self.b[act_id]

            # Solve theta_a = A_a^-1 @ b_a
            theta_a = np.linalg.solve(A_a, b_a)

            # Compute variance term x^T A_a^-1 x
            A_inv_x = np.linalg.solve(A_a, x)
            var_term = float(np.dot(x, A_inv_x))
            var_term = max(0.0, var_term)

            exploitation_term = float(np.dot(theta_a, x))
            exploration_bonus = float(self.alpha * np.sqrt(var_term))
            ucb_score = exploitation_term + exploration_bonus

            scores[act_id] = {
                "theta_dot_x": exploitation_term,
                "bonus": exploration_bonus,
                "ucb_score": ucb_score,
                "pull_count": self.arm_pull_counts[act_id],
            }

        return scores

    def select_action(
        self,
        context: Dict[str, Any],
        candidates: Sequence[RecoveryAction],
        attempt_number: int = 1,
    ) -> V2PolicyDecision:
        """
        Selects the candidate RecoveryAction with the highest UCB score.
        Preserves candidate order for deterministic tie-breaking.
        """
        scores = self.get_action_scores(context, candidates)

        best_candidate: Optional[RecoveryAction] = None
        best_score = float("-inf")

        for cand in candidates:
            act_id = cand.action_id
            score = scores[act_id]["ucb_score"]
            if score > best_score:
                best_score = score
                best_candidate = cand

        assert best_candidate is not None, "Candidate selection failed."

        details = {
            "attempt_number": attempt_number,
            "policy": "V2LinUCBPolicy",
            "alpha": self.alpha,
            "action_scores": scores,
            "chosen_action_id": best_candidate.action_id,
            "chosen_action_type": best_candidate.action_type,
            "chosen_target_method": best_candidate.target_method,
            "chosen_delay": best_candidate.delay,
            "chosen_ucb_score": best_score,
        }
        self.last_decision_details = details

        return V2PolicyDecision(
            action_chosen=best_candidate,
            action_id=best_candidate.action_id,
            expected_value=best_score,
            metadata=details,
        )

    def update(self, context: Dict[str, Any], action_id: str, reward: float) -> None:
        """
        Updates closed-form ridge regression state (A_a, b_a) for the specified action_id.
        Raises KeyError if action_id is not registered.
        """
        if action_id not in self.A:
            raise KeyError(f"Unknown action_id '{action_id}' for V2 policy update.")

        x = self.encoder.encode(context)
        self.A[action_id] += np.outer(x, x)
        self.b[action_id] += float(reward) * x
        self.arm_pull_counts[action_id] += 1
