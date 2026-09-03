"""
EVALUATION ONLY.
This oracle accesses simulator ground truth and must NEVER be imported by
production policy or API modules (api/, policies/).

Labeled: Evaluation-only theoretical upper bound. Not deployable and not part
of the RecoverFlow production decision path.
"""

from typing import Any, Dict, Tuple
from bandit_retry_scheduler.policies.base import BasePolicy, PolicyDecision
from bandit_retry_scheduler.simulator.config import DEFAULT_RETRY_COST, DELAY_ARMS
from bandit_retry_scheduler.simulator.ground_truth import calculate_recovery_probability


class OraclePolicy(BasePolicy):
    """
    Ground-Truth Greedy Oracle (Evaluation Only).

    Uses hidden simulator recovery probabilities to select the retry action with the highest
    immediate expected net value E[R] = P_true(recover | context, arm) * amount - retry_cost.
    Stops if maximum immediate expected net value across all candidate arms is <= 0.

    EVALUATION DISCLAIMER:
    The Oracle uses hidden simulator recovery probabilities and selects the retry action with the
    highest immediate expected net value for the current decision. It is evaluation-only and is
    not a production policy. It is a ground-truth reference benchmark, not necessarily a globally
    optimal sequential policy across the entire retry trajectory.
    """

    def __init__(self, max_attempts: int = 4, retry_cost: float = DEFAULT_RETRY_COST):
        super().__init__(max_attempts=max_attempts)
        self.retry_cost = retry_cost

    def get_expected_net_value(self, context: Dict[str, Any], arm: str) -> float:
        """
        Calculates expected net value E[R] = P(recover | context, arm) * amount - retry_cost.
        """
        amount = float(context.get("amount", 0.0))
        prob = calculate_recovery_probability(context, arm)
        expected_gross = prob * amount
        return expected_gross - self.retry_cost

    def select_arm(self, context: Dict[str, Any], attempt_number: int) -> PolicyDecision:
        if attempt_number < 1:
            raise ValueError(f"attempt_number must be >= 1, got {attempt_number}")

        best_arm = None
        max_ev = float("-inf")
        ev_map = {}

        for arm in DELAY_ARMS:
            ev = self.get_expected_net_value(context, arm)
            ev_map[arm] = ev
            if ev > max_ev:
                max_ev = ev
                best_arm = arm

        # Oracle stopping rule: if max expected net value <= 0, stop retrying
        if max_ev <= 0.0 or best_arm is None:
            return PolicyDecision(
                arm_chosen="NONE",
                expected_value=max_ev,
                metadata={"attempt_number": attempt_number, "policy": "oracle", "stop_reason": "negative_expected_value"},
            )

        return PolicyDecision(
            arm_chosen=best_arm,
            expected_value=max_ev,
            metadata={"attempt_number": attempt_number, "policy": "oracle", "ev_map": ev_map},
        )

    def should_stop(
        self,
        context: Dict[str, Any],
        attempt_number: int = 1,
        previous_success: bool = False,
    ) -> Tuple[bool, str]:
        stop, reason = super().should_stop(context, attempt_number, previous_success)
        if stop:
            return stop, reason

        decision = self.select_arm(context, attempt_number=attempt_number)
        if decision.arm_chosen == "NONE":
            return True, "oracle_negative_expected_value"

        return False, "eligible"
