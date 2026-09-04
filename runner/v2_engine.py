"""
v2_engine.py
Execution engine for RecoverFlow V2.
Runs V2 Action-Aware policies against the pure synthetic V2RetrySimulator.
Handles multi-attempt retry lifecycles, pure context transitions, and audit logging.
"""

from typing import Any, Dict, List, Optional
from bandit_retry_scheduler.api.v2_action_executor import execute_v2_retry_action
from bandit_retry_scheduler.api.v2_decision_service import V2DecisionService
from bandit_retry_scheduler.api.v2_feedback_loop import process_v2_outcome_and_update
from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.core.action_registry import ActionRegistry
from bandit_retry_scheduler.core.v2_context_transition import transition_v2_context
from bandit_retry_scheduler.policies.v2_linucb import V2LinUCBPolicy
from bandit_retry_scheduler.simulator.v2_environment import V2RetrySimulator, V2_TIMED_RETRY_COST


class V2PolicyExecutionEngine:
    """
    Executes a V2 action-aware policy on a stream of failed transactions.
    Uses pure, side-effect-free context advancement via transition_v2_context.
    """

    def __init__(
        self,
        simulator: Optional[V2RetrySimulator] = None,
        registry: Optional[ActionRegistry] = None,
    ):
        self.simulator = simulator or V2RetrySimulator()
        self.registry = registry or ActionRegistry()
        self.decision_service = V2DecisionService(registry=self.registry)

    def process_transaction(
        self,
        initial_context: Dict[str, Any],
        policy: V2LinUCBPolicy,
        logger: AuditLogger,
        evaluation_seed: Optional[int] = None,
        use_crn: bool = False,
    ) -> bool:
        """
        Processes a single failed transaction through its multi-attempt V2 lifecycle.

        Returns:
        --------
        bool: True if transaction was successfully recovered, False otherwise.
        """
        current_ctx = dict(initial_context)

        attempt_number = 1
        success = False

        while True:
            # 1. Get V2 retry decision via decision service
            decision = self.decision_service.get_v2_retry_decision(
                transaction=current_ctx,
                attempt_number=attempt_number,
                previous_success=success,
            )

            # Check if decision says stop / no retry
            if not decision.get("should_retry"):
                break

            # 2. Execute decision against pure simulator environment
            exec_result = execute_v2_retry_action(
                transaction=current_ctx,
                decision=decision,
                simulator=self.simulator,
                attempt_number=attempt_number,
                evaluation_seed=evaluation_seed,
                use_crn=use_crn,
            )

            action_taken = exec_result.get("action_taken")
            if action_taken != "retry":
                break

            # 3. Online feedback loop update
            process_v2_outcome_and_update(
                transaction=current_ctx,
                decision=decision,
                execution_result=exec_result,
                policy=policy,
                audit_logger=logger,
            )

            success = (exec_result.get("outcome") == "success")

            # If retry succeeded, stop immediately
            if success:
                break

            # If retry failed, compute pure next context state
            action_chosen = decision["action_chosen"]
            current_ctx = transition_v2_context(
                context=current_ctx,
                action=action_chosen,
                outcome=exec_result,
            )
            attempt_number += 1

        return success

    def run(
        self,
        transactions: List[Dict[str, Any]],
        policy: V2LinUCBPolicy,
        logger: Optional[AuditLogger] = None,
        evaluation_seed: Optional[int] = None,
        use_crn: bool = False,
    ) -> AuditLogger:
        """
        Runs the V2 policy over the full stream of failed transactions.
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
