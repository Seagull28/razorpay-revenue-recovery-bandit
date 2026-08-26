"""
base.py
Abstract base class and data structures for retry scheduling policies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from bandit_retry_scheduler.simulator.config import FailureCode


@dataclass
class PolicyDecision:
    """Represents a decision made by a retry scheduling policy."""
    arm_chosen: str
    expected_value: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class BasePolicy(ABC):
    """
    Abstract interface for all retry policies (fixed schedule, LinUCB, etc.).
    """

    def __init__(self, max_attempts: int = 4):
        self.max_attempts = max_attempts

    @abstractmethod
    def select_arm(self, context: Dict[str, Any], attempt_number: int) -> PolicyDecision:
        """
        Selects a retry delay arm for the given context and attempt number.

        Parameters:
        -----------
        context: Dict containing transaction features and metadata
        attempt_number: int (1-indexed attempt, 1 to max_attempts)

        Returns:
        --------
        PolicyDecision with arm_chosen and optional expected_value
        """
        pass

    def should_stop(
        self,
        context: Dict[str, Any],
        attempt_number: int,
        previous_success: bool = False,
    ) -> Tuple[bool, str]:
        """
        Universal safety stopping rules (Section 6 of Design Doc):
        1. Stop if previous attempt succeeded.
        2. Hard-stop after attempt 1 if failure_code == 'card_expired'.
        3. Hard-stop if attempt_number > max_attempts.

        Returns:
        --------
        (should_stop: bool, reason: str)
        """
        if previous_success:
            return True, "payment_recovered"

        failure_code = context.get("failure_code")
        if failure_code == FailureCode.CARD_EXPIRED.value and attempt_number > 1:
            return True, "hard_stop_card_expired"

        if attempt_number > self.max_attempts:
            return True, f"max_attempts_reached_{self.max_attempts}"

        return False, "continue"
