"""
linucb_adaptive_threshold.py
Item 3: LinUCB Policy variant with Per-Segment-Adaptive Cold-Start Stopping Thresholds.
Extends LinUCBPolicy as a separate class (policies/linucb.py remains untouched and locked).

Design Rationale:
Keys the min_samples_for_stopping safeguard off the failure code's amount distribution category:
- High-ticket failure codes ('insufficient_funds', 'do_not_honor'): min_samples = 25 (higher sample threshold
  before EV stopping rule evaluates, preventing premature pruning in high-variance, high-ticket contexts).
- Standard failure codes ('issuer_timeout', 'generic_decline', 'card_expired'): min_samples = 15 (canonical threshold).
"""

from typing import Any, Dict, Tuple
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.simulator.config import (
    AMOUNT_DISTRIBUTION_MAPPING,
    DEFAULT_RETRY_COST,
)


class LinUCBAdaptiveThresholdPolicy(LinUCBPolicy):
    """
    LinUCB policy variant implementing segment-adaptive cold-start stopping safeguards.
    High-ticket failure codes require 25 pulls per arm before EV stopping rule can trigger.
    Standard failure codes require 15 pulls per arm.
    """

    def __init__(
        self,
        alpha: float = 1.0,
        high_ticket_min_samples: int = 25,
        standard_min_samples: int = 15,
        max_attempts: int = 4,
    ):
        super().__init__(
            alpha=alpha,
            min_samples_for_stopping=standard_min_samples,
            max_attempts=max_attempts,
        )
        self.high_ticket_min_samples = high_ticket_min_samples
        self.standard_min_samples = standard_min_samples

    def get_segment_min_samples(self, failure_code: str) -> int:
        """Returns the cold-start sample threshold based on failure code category."""
        dist_type = AMOUNT_DISTRIBUTION_MAPPING.get(failure_code, "standard")
        if dist_type == "high_ticket":
            return self.high_ticket_min_samples
        return self.standard_min_samples

    def should_stop(
        self,
        context: Dict[str, Any],
        attempt_number: int,
        previous_success: bool = False,
    ) -> Tuple[bool, str]:
        """
        Segment-adaptive stopping rule evaluation:
        1. Universal safety rules (previous success, card_expired, max_attempts cap).
        2. Attempt 1 always continues.
        3. Determine segment-specific min_samples requirement (25 for high-ticket, 15 for standard).
        4. If any arm has pull count < min_samples for this segment, force continue.
        5. Once mature, evaluate currency-denominated EV rule: max_a(theta_a^T x) <= 0.
        """
        # 1. Base safety stopping rules (card_expired attempt > 1, max_attempts cap)
        base_stop, base_reason = super(LinUCBPolicy, self).should_stop(
            context, attempt_number, previous_success
        )
        if base_stop:
            return True, base_reason

        # 2. Force continuation on first attempt
        if attempt_number == 1:
            return False, "continue_attempt_1"

        # 3. Check segment-specific cold-start safeguard
        failure_code = context.get("failure_code", "generic_decline")
        required_min_samples = self.get_segment_min_samples(failure_code)

        all_arms_mature = all(
            self.arm_pull_counts[arm] >= required_min_samples for arm in self.arms
        )

        if not all_arms_mature:
            min_pulls = min(self.arm_pull_counts.values())
            return (
                False,
                f"cold_start_safeguard_active_min_{min_pulls}_lt_{required_min_samples}_for_{failure_code}",
            )

        # 4. Mature stage EV stopping check
        arm_scores = self.get_arm_scores(context)
        max_theta_dot_x = max(scores["theta_dot_x"] for scores in arm_scores.values())

        if max_theta_dot_x <= 0.0:
            return (
                True,
                f"expected_net_value_negative_{max_theta_dot_x:.2f}_inr",
            )

        return False, "continue_positive_expected_value"
