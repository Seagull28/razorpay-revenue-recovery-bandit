"""
recovery_action.py
Domain abstraction for recovery actions in RecoverFlow V2.
Generic immutable value object representing a recovery action.
"""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class RecoveryAction:
    """
    Structured representation of a recovery action for RecoverFlow V2.

    Fields:
    -------
    action_id: str
        Stable identifier used as the bandit arm identity across decision,
        execution, feedback, and learning updates.
    action_type: str
        Category of recovery action (e.g., "TIMED_RETRY", "METHOD_SWITCH").
    source_method: str
        The initial/current payment method (e.g., "card").
    target_method: str
        The target payment method for recovery (e.g., "card", "upi").
    delay: str
        The timing delay window associated with the action (e.g., "1d", "0").
    """

    action_id: str
    action_type: str
    source_method: str
    target_method: str
    delay: str

    def __post_init__(self) -> None:
        """Enforces structural integrity validation rules upon construction."""
        if not isinstance(self.action_id, str) or not self.action_id.strip():
            raise ValueError("action_id must be a non-empty string.")

        if not isinstance(self.action_type, str) or not self.action_type.strip():
            raise ValueError("action_type must be a non-empty string.")

        if not isinstance(self.source_method, str) or not self.source_method.strip():
            raise ValueError("source_method must be a non-empty string.")

        if not isinstance(self.target_method, str) or not self.target_method.strip():
            raise ValueError("target_method must be a non-empty string.")

        if not isinstance(self.delay, str) or not self.delay.strip():
            raise ValueError("delay must be a non-empty string.")

    def to_dict(self) -> Dict[str, Any]:
        """Converts the RecoveryAction instance to a dictionary representation."""
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "source_method": self.source_method,
            "target_method": self.target_method,
            "delay": self.delay,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecoveryAction":
        """Constructs a RecoveryAction instance from a dictionary."""
        return cls(
            action_id=data["action_id"],
            action_type=data["action_type"],
            source_method=data["source_method"],
            target_method=data["target_method"],
            delay=data["delay"],
        )
