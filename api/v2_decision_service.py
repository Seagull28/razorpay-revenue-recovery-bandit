"""
v2_decision_service.py
Core Recovery Decision API for RecoverFlow V2.
Integrates V2 eligibility pre-checks, ActionRegistry candidates, V2LinUCBPolicy, and audit logging.
"""

from typing import Any, Dict, Optional
from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.core.action_registry import ActionRegistry
from bandit_retry_scheduler.core.recovery_action import RecoveryAction
from bandit_retry_scheduler.core.v2_ev_estimator import V2EVEstimator
from bandit_retry_scheduler.api.v2_eligibility import check_v2_eligibility
from bandit_retry_scheduler.policies.v2_linucb import V2LinUCBPolicy, V2PolicyDecision


class V2DecisionService:
    """
    Service wrapping V2 LinUCB policy, ActionRegistry, eligibility gate, EV estimator, and audit logging into a single API.
    """

    def __init__(
        self,
        policy: Optional[V2LinUCBPolicy] = None,
        registry: Optional[ActionRegistry] = None,
        audit_logger: Optional[AuditLogger] = None,
        ev_estimator: Optional[V2EVEstimator] = None,
    ):
        self.registry = registry if registry is not None else ActionRegistry()
        self.policy = policy if policy is not None else V2LinUCBPolicy(registry=self.registry)
        self.ev_estimator = ev_estimator if ev_estimator is not None else V2EVEstimator(registry=self.registry)
        if hasattr(self.policy, "__dict__"):
            self.policy.ev_estimator = self.ev_estimator
        self.audit_logger = audit_logger

    def get_v2_retry_decision(
        self,
        transaction: Dict[str, Any],
        attempt_number: int = 1,
        previous_success: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluates a V2 recovery decision for a given transaction context.

        Raises:
        -------
        ValueError: If 'source_method' is missing or invalid in transaction context.
        """
        tx_id = transaction.get("transaction_id", "unknown_tx")

        # Validate source_method presence
        source_method = transaction.get("source_method")
        if not isinstance(source_method, str) or not source_method.strip():
            raise ValueError("Missing or invalid 'source_method' in V2 context.")

        # Ensure policy retains reference to ev_estimator
        if self.ev_estimator is not None and hasattr(self.policy, "__dict__"):
            self.policy.ev_estimator = self.ev_estimator

        # 1. Retrieve candidates from ActionRegistry
        candidates = self.registry.get_candidates(source_method)

        # 2. Contextual Safety Eligibility Gate pre-check
        eligible, eligible_candidates, gate_reason = check_v2_eligibility(
            context=transaction,
            candidates=candidates,
            attempt_number=attempt_number,
            previous_success=previous_success,
            max_attempts=self.policy.max_attempts,
        )

        if not eligible or not eligible_candidates:
            result = {
                "transaction_id": tx_id,
                "should_retry": False,
                "action_chosen": None,
                "action_id": None,
                "expected_net_value_inr": 0.0,
                "stop_reason": gate_reason,
            }
            if self.audit_logger:
                self.audit_logger.log(
                    transaction_id=tx_id,
                    timestamp=transaction.get("simulated_day", 1),
                    context_vector=transaction,
                    arm_chosen="NONE",
                    expected_value=0.0,
                    actual_outcome=0,
                    amount_recovered=0.0,
                    reward=0.0,
                )
            return result

        # 3. Economic EV Feasibility Gate
        if self.ev_estimator is not None:
            is_feasible, best_act, max_ev, action_evs = self.ev_estimator.evaluate_economic_feasibility(
                context=transaction,
                eligible_candidates=eligible_candidates,
            )
            if not is_feasible:
                result = {
                    "transaction_id": tx_id,
                    "should_retry": False,
                    "action_chosen": None,
                    "action_id": None,
                    "expected_net_value_inr": round(max_ev, 2),
                    "stop_reason": "non_positive_expected_value",
                    "metadata": {"max_ev": max_ev, "action_evs": action_evs},
                }
                if self.audit_logger:
                    self.audit_logger.log(
                        transaction_id=tx_id,
                        timestamp=transaction.get("simulated_day", 1),
                        context_vector=transaction,
                        arm_chosen="NONE",
                        expected_value=round(max_ev, 2),
                        actual_outcome=0,
                        amount_recovered=0.0,
                        reward=0.0,
                    )
                return result

        # 4. Eligible & EV Positive -> Select optimal candidate RecoveryAction via V2LinUCBPolicy
        policy_decision = self.policy.select_action(
            context=transaction,
            candidates=eligible_candidates,
            attempt_number=attempt_number,
        )

        chosen_action = policy_decision.action_chosen
        expected_net_val = float(policy_decision.expected_value) if policy_decision.expected_value is not None else 0.0

        should_retry = (chosen_action is not None)
        stop_reason = policy_decision.metadata.get("reason") if not should_retry else None

        result = {
            "transaction_id": tx_id,
            "should_retry": should_retry,
            "action_chosen": chosen_action,
            "action_id": policy_decision.action_id if should_retry else None,
            "expected_net_value_inr": round(expected_net_val, 2),
            "stop_reason": stop_reason,
            "metadata": policy_decision.metadata,
        }

        if self.audit_logger:
            self.audit_logger.log(
                transaction_id=tx_id,
                timestamp=transaction.get("simulated_day", 1),
                context_vector=transaction,
                arm_chosen=policy_decision.action_id if should_retry else "NONE",
                expected_value=expected_net_val,
                actual_outcome=0,
                amount_recovered=0.0,
                reward=0.0,
            )

        return result


def get_v2_retry_decision(
    transaction: Dict[str, Any],
    policy: Optional[V2LinUCBPolicy] = None,
    registry: Optional[ActionRegistry] = None,
    attempt_number: int = 1,
    previous_success: bool = False,
    audit_logger: Optional[AuditLogger] = None,
    ev_estimator: Optional[V2EVEstimator] = None,
) -> Dict[str, Any]:
    """Convenience function wrapper for V2DecisionService."""
    service = V2DecisionService(policy=policy, registry=registry, audit_logger=audit_logger, ev_estimator=ev_estimator)
    return service.get_v2_retry_decision(
        transaction=transaction,
        attempt_number=attempt_number,
        previous_success=previous_success,
    )

