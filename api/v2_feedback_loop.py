"""
v2_feedback_loop.py
Online Feedback Loop for RecoverFlow V2.
Wires outcome results from execute_v2_retry_action() back into policy.update(transaction, action_id, reward)
and logs completed execution records in AuditLogger.
"""

from typing import Any, Dict, Optional
from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.policies.v2_linucb import V2LinUCBPolicy


def process_v2_outcome_and_update(
    transaction: Dict[str, Any],
    decision: Dict[str, Any],
    execution_result: Dict[str, Any],
    policy: V2LinUCBPolicy,
    audit_logger: Optional[AuditLogger] = None,
) -> None:
    """
    Processes execution outcome and updates V2 policy parameters online.

    Parameters:
    -----------
    transaction: dict containing context vector / features
    decision: dict returned by get_v2_retry_decision()
    execution_result: dict returned by execute_v2_retry_action()
    policy: V2LinUCBPolicy instance
    audit_logger: Optional AuditLogger instance
    """
    action_taken = execution_result.get("action_taken")

    # If no retry action was taken, there is no outcome to update policy with
    if action_taken != "retry":
        return

    action_id = execution_result.get("action_id")
    reward = float(execution_result.get("reward", 0.0))
    outcome_str = execution_result.get("outcome")
    actual_outcome = 1 if outcome_str == "success" else 0
    amount_recovered = float(execution_result.get("amount_recovered", 0.0))

    if not action_id:
        return

    # 1. Update policy internal state online (delegates to V2LinUCBPolicy.update)
    policy.update(transaction, action_id, reward)

    # 2. Update EV estimator online if present on policy
    ev_estimator = getattr(policy, "ev_estimator", None)
    if ev_estimator is not None and hasattr(ev_estimator, "update"):
        ev_estimator.update(transaction, action_id, outcome_str == "success")

    # 3. Append completed outcome record to audit logger
    if audit_logger is not None:
        tx_id = transaction.get("transaction_id", "unknown_tx")
        timestamp = transaction.get("simulated_day", 1)
        expected_value = decision.get("expected_net_value_inr")

        audit_logger.log(
            transaction_id=tx_id,
            timestamp=timestamp,
            context_vector=transaction,
            arm_chosen=action_id,
            expected_value=expected_value,
            actual_outcome=actual_outcome,
            amount_recovered=amount_recovered,
            reward=reward,
        )
