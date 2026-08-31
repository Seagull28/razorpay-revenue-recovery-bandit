"""
feedback_loop.py
Online Feedback Loop for RecoverFlow (Phase 5 Tier 2).
Wires outcome results from execute_retry_action() back into the policy's update() method
and logs completed transaction records in AuditLogger.
"""

from typing import Any, Dict, Optional
from bandit_retry_scheduler.policies.base import BasePolicy
from bandit_retry_scheduler.audit.logger import AuditLogger


def process_outcome_and_update(
    transaction: Dict[str, Any],
    decision: Dict[str, Any],
    execution_result: Dict[str, Any],
    policy: BasePolicy,
    audit_logger: Optional[AuditLogger] = None,
) -> None:
    """
    Processes execution outcome and updates policy parameters online.

    Parameters:
    -----------
    transaction: dict containing context vector / features
    decision: dict returned by get_retry_decision()
    execution_result: dict returned by execute_retry_action()
    policy: BasePolicy instance (e.g. LinUCBPolicy)
    audit_logger: Optional AuditLogger instance to record outcome
    """
    action_taken = execution_result.get("action_taken")

    # If no retry action was taken, there is no outcome to update policy with
    if action_taken != "retry":
        return

    delay_executed = execution_result.get("delay_executed")
    reward = execution_result.get("reward", 0.0)
    outcome_str = execution_result.get("outcome")
    actual_outcome = 1 if outcome_str == "success" else 0
    amount_recovered = execution_result.get("amount_recovered", 0.0)

    # 1. Update policy internal state online (delegates to existing policy.update method)
    if hasattr(policy, "update"):
        policy.update(transaction, delay_executed, reward)

    # 2. Append completed outcome record to audit logger
    if audit_logger is not None:
        tx_id = transaction.get("transaction_id", "unknown_tx")
        timestamp = transaction.get("simulated_day", 1)
        expected_value = decision.get("expected_net_value_inr")

        audit_logger.log(
            transaction_id=tx_id,
            timestamp=timestamp,
            context_vector=transaction,
            arm_chosen=str(delay_executed),
            expected_value=expected_value,
            actual_outcome=actual_outcome,
            amount_recovered=amount_recovered,
            reward=reward,
        )
