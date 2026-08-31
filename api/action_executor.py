"""
action_executor.py
Bounded Action Execution engine for RecoverFlow (Phase 5 Tier 2).
Executes retry recommendations from get_retry_decision() against the simulator.
Enforces safety boundaries so stopped decisions can NEVER trigger retry actions.
"""

from typing import Any, Dict
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.config import DEFAULT_RETRY_COST


def execute_retry_action(
    transaction: Dict[str, Any],
    decision: Dict[str, Any],
    simulator: RetrySimulator,
) -> Dict[str, Any]:
    """
    Executes a retry decision against the simulator environment.

    SAFETY CAPABILITY:
    If decision['should_retry'] is False, this function strictly rejects execution
    and returns a 'no_action' record. It will never invoke the simulator.

    Parameters:
    -----------
    transaction: dict containing context vector / transaction details
    decision: dict returned by get_retry_decision()
    simulator: RetrySimulator instance

    Returns:
    --------
    Execution record dict with keys:
    - transaction_id: str
    - action_taken: "retry" | "no_action"
    - delay_executed: Optional[str]
    - outcome: "success" | "failure" | "not_attempted"
    - amount_recovered: float
    - reward: float
    """
    tx_id = transaction.get("transaction_id", "unknown_tx")
    should_retry = decision.get("should_retry", False)
    recommended_delay = decision.get("recommended_delay")

    # SAFETY GATE BOUNDARY: Force no-op if decision says should_retry is False
    if not should_retry or not recommended_delay:
        return {
            "transaction_id": tx_id,
            "action_taken": "no_action",
            "delay_executed": None,
            "outcome": "not_attempted",
            "amount_recovered": 0.0,
            "reward": 0.0,
        }

    # Execute retry via existing simulator environment (no reimplemented math)
    success, amount_recovered = simulator.simulate_retry(transaction, recommended_delay)
    outcome = "success" if success else "failure"

    # Reward calculation conforming to Section 5: recovered amount minus retry cost if success, else -cost
    reward = (amount_recovered - DEFAULT_RETRY_COST) if success else -DEFAULT_RETRY_COST

    return {
        "transaction_id": tx_id,
        "action_taken": "retry",
        "delay_executed": recommended_delay,
        "outcome": outcome,
        "amount_recovered": round(float(amount_recovered), 2),
        "reward": round(float(reward), 2),
    }
