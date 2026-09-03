"""
engine.py
Execution engine that runs retry scheduling policies against the synthetic transaction simulator.
Handles multi-attempt retry loops, temporal advancement, state updates, and audit logging.
"""

from typing import Any, Dict, List, Optional
from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.policies.base import BasePolicy
from bandit_retry_scheduler.simulator.config import DEFAULT_RETRY_COST, DelayArm
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.ground_truth import to_day_bucket, to_failure_bucket


# Duration in simulated days added per delay arm
DELAY_TO_DAYS_MAP: Dict[str, int] = {
    DelayArm.HOUR_1.value: 0,
    DelayArm.HOUR_6.value: 0,
    DelayArm.DAY_1.value: 1,
    DelayArm.DAY_3.value: 3,
    DelayArm.DAY_7.value: 7,
}


def advance_transaction_context(context: Dict[str, Any], delay_chosen: str) -> Dict[str, Any]:
    """
    Advances a failed transaction's context state to the next retry attempt:
    1. Advances simulated_day by the delay duration in days.
    2. Updates day_of_month and recalculates day_of_month_bucket.
    3. Increments retry_attempt_number.
    4. Increments customer_prior_failures_this_cycle ('0' -> '1' -> '2+').
    """
    new_ctx = dict(context)

    # 1. Advance simulated time
    days_delta = DELAY_TO_DAYS_MAP.get(delay_chosen, 0)
    current_day = new_ctx.get("simulated_day", 1)
    next_day = current_day + days_delta
    new_ctx["simulated_day"] = next_day

    # 2. Update day of month and salary bucket
    day_of_month = ((next_day - 1) % 31) + 1
    new_ctx["day_of_month"] = day_of_month
    new_ctx["day_of_month_bucket"] = to_day_bucket(day_of_month)

    # 3. Increment attempt number
    current_attempt = new_ctx.get("retry_attempt_number", 1)
    new_ctx["retry_attempt_number"] = current_attempt + 1

    # 4. Increment failure count in this cycle
    current_fail = str(new_ctx.get("customer_prior_failures_this_cycle", "0"))
    if current_fail == "0":
        new_ctx["customer_prior_failures_this_cycle"] = "1"
    else:
        new_ctx["customer_prior_failures_this_cycle"] = "2+"

    return new_ctx


class PolicyExecutionEngine:
    """
    Executes a retry scheduling policy on a stream of transactions.
    """

    def __init__(
        self,
        simulator: Optional[RetrySimulator] = None,
        retry_cost: float = DEFAULT_RETRY_COST,
    ):
        self.simulator = simulator or RetrySimulator()
        self.retry_cost = retry_cost

    def process_transaction(
        self,
        initial_context: Dict[str, Any],
        policy: BasePolicy,
        logger: AuditLogger,
        evaluation_seed: Optional[int] = None,
        use_crn: bool = False,
    ) -> bool:
        """
        Processes a single failed transaction through the policy's multi-attempt lifecycle.

        Returns:
        --------
        bool: True if transaction was successfully recovered, False otherwise.
        """
        current_ctx = dict(initial_context)
        attempt_number = 1
        success = False

        while True:
            # Check universal stopping rules
            stop, reason = policy.should_stop(
                current_ctx,
                attempt_number=attempt_number,
                previous_success=success,
            )
            if stop:
                break

            # Policy selects delay arm
            decision = policy.select_arm(current_ctx, attempt_number=attempt_number)
            arm = decision.arm_chosen

            # Simulate retry attempt
            success, amount_recovered = self.simulator.simulate_retry(
                current_ctx,
                arm,
                attempt_number=attempt_number,
                evaluation_seed=evaluation_seed,
                use_crn=use_crn,
            )

            # Compute net reward: (amount_recovered if success else 0) - retry_cost
            reward = (amount_recovered if success else 0.0) - self.retry_cost

            # Log decision per Section 7 schema
            logger.log(
                transaction_id=current_ctx["transaction_id"],
                timestamp=f"day_{current_ctx.get('simulated_day', 1)}_att_{attempt_number}",
                context_vector=current_ctx,
                arm_chosen=arm,
                expected_value=decision.expected_value,
                actual_outcome=1 if success else 0,
                amount_recovered=amount_recovered,
                reward=reward,
            )

            # Online adaptive learning: update policy immediately on observed reward
            if hasattr(policy, "update") and callable(getattr(policy, "update")):
                policy.update(current_ctx, arm, reward)

            # If retry succeeded, stop immediately
            if success:
                break

            # If retry failed, advance context state for next attempt
            current_ctx = advance_transaction_context(current_ctx, arm)
            attempt_number += 1

        return success

    def run(
        self,
        transactions: List[Dict[str, Any]],
        policy: BasePolicy,
        logger: Optional[AuditLogger] = None,
        evaluation_seed: Optional[int] = None,
        use_crn: bool = False,
    ) -> AuditLogger:
        """
        Runs the policy over the full stream of failed transactions.
        """
        audit_logger = logger or AuditLogger()
        for tx in transactions:
            self.process_transaction(
                tx,
                policy,
                audit_logger,
                evaluation_seed=evaluation_seed,
                use_crn=use_crn,
            )
        return audit_logger
