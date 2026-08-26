"""
linucb.py
Disjoint Linear Upper Confidence Bound (LinUCB) contextual bandit policy with
currency-denominated Expected-Value stopping rule and cold-start safeguards.
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from bandit_retry_scheduler.policies.base import BasePolicy, PolicyDecision
from bandit_retry_scheduler.policies.encoder import ContextVectorEncoder
from bandit_retry_scheduler.simulator.config import DEFAULT_RETRY_COST, DELAY_ARMS, FailureCode


class LinUCBPolicy(BasePolicy):
    """
    Disjoint LinUCB contextual bandit algorithm (Li et al., 2010).
    Maintains independent ridge regression models (A_a, b_a) per arm.

    Arm selection:
    For each arm a in DELAY_ARMS:
        A_a_inv = inv(A_a)
        theta_a = A_a_inv @ b_a
        exploitation_term = theta_a^T x (expected net reward in INR)
        exploration_bonus = alpha * sqrt(x^T A_a_inv x)
        ucb_score = exploitation_term + exploration_bonus
    Select a* = argmax_a (ucb_score)

    Stopping Rule:
    - Card expired: Hard stop after attempt 1.
    - Max attempts: Hard stop after max_attempts (4).
    - Success: Stop immediately upon recovery.
    - Continuation Rule (attempt k >= 2):
      Evaluates point estimate of expected net revenue: max_a (theta_a^T x).
      If max_a (theta_a^T x) <= 0.0 AND arm has sufficient observation count
      (>= min_samples_for_stopping), retries halt.
      During cold start (< min_samples_for_stopping), falls back to 'continue'
      to prevent premature pruning before point estimates have matured.
    """

    def __init__(
        self,
        alpha: float = 1.0,
        max_attempts: int = 4,
        retry_cost: float = DEFAULT_RETRY_COST,
        stopping_mode: str = "expected_value",  # "expected_value" or "tau_decay" (legacy)
        min_samples_for_stopping: int = 5,
        soft_decay_base_threshold: float = 0.0,
    ):
        super().__init__(max_attempts=max_attempts)
        self.alpha = float(alpha)
        self.retry_cost = float(retry_cost)
        self.stopping_mode = stopping_mode
        self.min_samples_for_stopping = int(min_samples_for_stopping)
        self.soft_decay_base_threshold = float(soft_decay_base_threshold)

        self.encoder = ContextVectorEncoder()
        self.d = self.encoder.DIMENSION  # 19 dimensions

        self.arms = list(DELAY_ARMS)
        self.n_arms = len(self.arms)

        # Initialize disjoint ridge regression state matrices per arm
        # A_a = I_d (ridge regularization with lambda=1.0)
        # b_a = 0_d
        self.A: Dict[str, np.ndarray] = {
            arm: np.eye(self.d, dtype=np.float64) for arm in self.arms
        }
        self.b: Dict[str, np.ndarray] = {
            arm: np.zeros(self.d, dtype=np.float64) for arm in self.arms
        }

        # Track sample counts per arm for cold-start stopping safeguard
        self.arm_pull_counts: Dict[str, int] = {arm: 0 for arm in self.arms}

        # Cache of latest decision scores for explainability and traces
        self.last_decision_details: Dict[str, Any] = {}

    def get_arm_scores(self, context: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        """
        Computes the point estimate (exploitation), uncertainty bonus (exploration),
        and combined UCB score for all 5 arms given the context vector x.

        Returns:
        --------
        Dict[arm, {
            'theta_dot_x': float (Point estimate of net reward in INR),
            'bonus': float (Uncertainty exploration bonus),
            'ucb_score': float (Combined UCB score),
            'pull_count': int
        }]
        """
        x = self.encoder.encode(context)
        scores: Dict[str, Dict[str, float]] = {}

        for arm in self.arms:
            A_a = self.A[arm]
            b_a = self.b[arm]

            # Solve for theta_a = A_a^-1 @ b_a
            theta_a = np.linalg.solve(A_a, b_a)

            # Compute variance term x^T A_a^-1 x
            A_inv_x = np.linalg.solve(A_a, x)
            var_term = float(np.dot(x, A_inv_x))
            var_term = max(0.0, var_term)

            exploitation_term = float(np.dot(theta_a, x))
            exploration_bonus = float(self.alpha * np.sqrt(var_term))
            ucb_score = exploitation_term + exploration_bonus

            scores[arm] = {
                "theta_dot_x": exploitation_term,
                "bonus": exploration_bonus,
                "ucb_score": ucb_score,
                "pull_count": self.arm_pull_counts[arm],
            }

        return scores

    def select_arm(self, context: Dict[str, Any], attempt_number: int) -> PolicyDecision:
        """
        Selects the arm with the highest UCB score for the given context.
        Arm selection strictly uses the full UCB score (exploitation + exploration bonus).
        """
        scores = self.get_arm_scores(context)

        best_arm = self.arms[0]
        best_score = float("-inf")

        for arm in self.arms:
            score = scores[arm]["ucb_score"]
            if score > best_score:
                best_score = score
                best_arm = arm

        details = {
            "attempt_number": attempt_number,
            "policy": "LinUCB",
            "alpha": self.alpha,
            "arm_scores": scores,
            "chosen_arm": best_arm,
            "chosen_theta_dot_x": scores[best_arm]["theta_dot_x"],
            "chosen_bonus": scores[best_arm]["bonus"],
            "chosen_ucb_score": scores[best_arm]["ucb_score"],
        }
        self.last_decision_details = details

        return PolicyDecision(
            arm_chosen=best_arm,
            expected_value=best_score,
            metadata=details,
        )

    def update(self, context: Dict[str, Any], arm_chosen: str, reward: float) -> None:
        """
        Updates the closed-form ridge regression state (A_a, b_a) for the chosen arm.

        A_a <- A_a + x @ x^T
        b_a <- b_a + r * x
        """
        if arm_chosen not in self.A:
            raise ValueError(f"Unknown arm: {arm_chosen}")

        x = self.encoder.encode(context)
        self.A[arm_chosen] += np.outer(x, x)
        self.b[arm_chosen] += float(reward) * x
        self.arm_pull_counts[arm_chosen] += 1

    def should_stop(
        self,
        context: Dict[str, Any],
        attempt_number: int,
        previous_success: bool = False,
    ) -> Tuple[bool, str]:
        """
        Evaluates stopping rules:
        1. Universal Hard-Stops:
           - Stop immediately if previous attempt succeeded.
           - Hard-stop after attempt 1 if failure_code == 'card_expired'.
           - Hard-stop if attempt_number > max_attempts (4).
        2. Expected-Value Stopping Rule (Phase 3.5 Correction):
           - At attempt k >= 2:
             Computes the maximum point estimate of expected net revenue across all arms:
                 max_ev = max_a (theta_a^T x)
             If max_ev <= 0.0:
                 Check cold-start safeguard: if the best candidate arm has fewer than
                 min_samples_for_stopping observations, fall back to 'continue'
                 to prevent premature termination on spuriously unformed estimates.
                 Otherwise, stop retrying because expected net revenue is non-positive.
        """
        # 1. Success check
        if previous_success:
            return True, "payment_recovered"

        # 2. Card expired hard-stop
        failure_code = context.get("failure_code")
        if failure_code == FailureCode.CARD_EXPIRED.value and attempt_number > 1:
            return True, "hard_stop_card_expired"

        # 3. Max attempts cap
        if attempt_number > self.max_attempts:
            return True, f"max_attempts_reached_{self.max_attempts}"

        # 4. Continuation evaluation for attempts >= 2
        if attempt_number >= 2:
            scores = self.get_arm_scores(context)

            if self.stopping_mode == "expected_value":
                # =================================================================
                # Currency-Denominated Expected-Value Stopping Rule (Phase 3.5):
                # Uses pure point estimate max_a (theta_a^T x) in INR (Rupees),
                # strictly distinct from the UCB score used for arm selection.
                # =================================================================
                best_arm = max(self.arms, key=lambda a: scores[a]["theta_dot_x"])
                max_ev = scores[best_arm]["theta_dot_x"]
                pulls = scores[best_arm]["pull_count"]

                # Cold-start safeguard: If the best arm has fewer than min_samples_for_stopping,
                # do not prune on negative point estimates — allow exploration to continue.
                if max_ev <= 0.0:
                    if pulls < self.min_samples_for_stopping:
                        return False, f"cold_start_safeguard_pulls_{pulls}_below_min_{self.min_samples_for_stopping}"
                    return True, f"expected_net_value_negative_{max_ev:.2f}_inr"

            elif self.stopping_mode == "tau_decay":
                # Legacy abstract UCB-score soft decay (for 3-way benchmarking)
                max_ucb = max(s["ucb_score"] for s in scores.values())
                thresh = self.soft_decay_base_threshold * float(attempt_number - 1)
                if max_ucb <= thresh:
                    return True, f"soft_decay_ev_below_threshold_{max_ucb:.2f}_vs_{thresh:.2f}"

        return False, "continue"
