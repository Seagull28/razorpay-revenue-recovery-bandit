"""
v2_action_executor.py
Bounded Action Execution engine for RecoverFlow V2.
Executes RecoveryAction decisions against the pure V2RetrySimulator environment.
Enforces safety boundaries so stopped decisions can NEVER trigger execution.
"""

from typing import Any, Dict, Optional
from bandit_retry_scheduler.core.recovery_action import RecoveryAction
from bandit_retry_scheduler.simulator.v2_environment import V2RetrySimulator


def execute_v2_retry_action(
    transaction: Dict[str, Any],
    decision: Dict[str, Any],
    simulator: V2RetrySimulator,
    attempt_number: Optional[int] = None,
    evaluation_seed: Optional[int] = None,
    use_crn: bool = False,
) -> Dict[str, Any]:
    """
    Executes a V2 retry decision against the V2 simulator environment.

    SAFETY GATE BOUNDARY:
    If decision['should_retry'] is False, strictly returns a 'no_action' record without invoking the simulator.

    Parameters:
    -----------
    transaction: dict containing context features
    decision: dict returned by get_v2_retry_decision()
    simulator: V2RetrySimulator instance
    attempt_number: Optional int current attempt count
    evaluation_seed: Optional int CRN seed for reproducible evaluation
    use_crn: bool whether to use Common Random Numbers

    Returns:
    --------
    Execution record dict with keys:
    - transaction_id: str
    - action_taken: "retry" | "no_action"
    - action_id: Optional[str]
    - action_chosen: Optional[RecoveryAction]
    - outcome: "success" | "failure" | "not_attempted"
    - amount_recovered: float
    - reward: float
    - action_cost: float
    """
    tx_id = transaction.get("transaction_id", "unknown_tx")
    should_retry = decision.get("should_retry", False)
    action_chosen = decision.get("action_chosen")

    if not should_retry or not isinstance(action_chosen, RecoveryAction):
        return {
            "transaction_id": tx_id,
            "action_taken": "no_action",
            "action_id": None,
            "action_chosen": None,
            "outcome": "not_attempted",
            "amount_recovered": 0.0,
            "reward": 0.0,
            "action_cost": 0.0,
        }

    # Execute action via pure simulator (no side-effects on context dict)
    outcome = simulator.simulate_action(
        transaction,
        action_chosen,
        attempt_number=attempt_number,
        evaluation_seed=evaluation_seed,
        use_crn=use_crn,
    )

    return {
        "transaction_id": tx_id,
        "action_taken": "retry",
        "action_id": outcome["action_id"],
        "action_chosen": action_chosen,
        "outcome": "success" if outcome["success"] else "failure",
        "amount_recovered": round(float(outcome["amount_recovered"]), 2),
        "reward": round(float(outcome["reward"]), 2),
        "action_cost": outcome["action_cost"],
    }
