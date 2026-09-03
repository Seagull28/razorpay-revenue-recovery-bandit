"""
decision_service.py
Core Recovery Decision API for RecoverFlow.
Provides get_retry_decision() which integrates eligibility pre-checks,
LinUCB policy evaluation, explainability engine, and audit logging.
"""

from typing import Any, Dict, Optional
from bandit_retry_scheduler.api.eligibility import check_eligibility
from bandit_retry_scheduler.api.explainability import generate_decision_explanation
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.policies.base import BasePolicy
from bandit_retry_scheduler.audit.logger import AuditLogger


class DecisionService:
    """
    Service wrapping LinUCB retry scheduling policy, eligibility gate,
    explainability generation, and audit logging into a single unified API.
    """

    def __init__(
        self,
        policy: Optional[BasePolicy] = None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        self.policy = policy if policy is not None else LinUCBPolicy()
        self.audit_logger = audit_logger

    def get_retry_decision(
        self,
        transaction: Dict[str, Any],
        attempt_number: int = 1,
        previous_success: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluates a retry decision for a given transaction.

        Parameters:
        -----------
        transaction: dict containing context features (transaction_id, amount, failure_code, bank, etc.)
        attempt_number: int attempt number (default 1)
        previous_success: bool whether previous attempt succeeded (default False)

        Returns:
        --------
        Dict with keys:
        - transaction_id: str
        - should_retry: bool
        - recommended_delay: Optional[str] (or None if should_retry=False)
        - expected_net_value_inr: float
        - stop_reason: Optional[str]
        - explanation: str
        - arm_scores: dict mapping each of the 5 arms to its score breakdown
        """
        tx_id = transaction.get("transaction_id", "unknown_tx")

        # 1. Eligibility Safety Gate pre-check
        eligible, gate_reason = check_eligibility(
            transaction=transaction,
            attempt_number=attempt_number,
            previous_success=previous_success,
            max_attempts=self.policy.max_attempts,
        )

        # Obtain full 5-arm score breakdown from policy for explainability
        arm_scores = {}
        if hasattr(self.policy, "get_arm_scores"):
            arm_scores = self.policy.get_arm_scores(transaction)

        if not eligible:
            result = {
                "transaction_id": tx_id,
                "should_retry": False,
                "recommended_delay": None,
                "expected_net_value_inr": 0.0,
                "stop_reason": gate_reason,
                "arm_scores": arm_scores,
            }
            result["explanation"] = generate_decision_explanation(transaction, result)
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

        # 2. Consult Bandit Policy stopping rule (e.g. EV stopping rule)
        should_stop, policy_stop_reason = self.policy.should_stop(
            context=transaction,
            attempt_number=attempt_number,
            previous_success=previous_success,
        )

        if should_stop:
            result = {
                "transaction_id": tx_id,
                "should_retry": False,
                "recommended_delay": None,
                "expected_net_value_inr": 0.0,
                "stop_reason": policy_stop_reason,
                "arm_scores": arm_scores,
            }
            result["explanation"] = generate_decision_explanation(transaction, result)
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

        # 3. Eligible & Continuing -> Select optimal arm via policy
        policy_decision = self.policy.select_arm(
            context=transaction,
            attempt_number=attempt_number,
        )

        recommended_delay = policy_decision.arm_chosen
        expected_net_val = float(policy_decision.expected_value) if policy_decision.expected_value is not None else 0.0

        # Retrieve updated arm scores from policy's decision details
        if hasattr(self.policy, "last_decision_details") and self.policy.last_decision_details:
            arm_scores = self.policy.last_decision_details.get("arm_scores", arm_scores)

        result = {
            "transaction_id": tx_id,
            "should_retry": True,
            "recommended_delay": recommended_delay,
            "expected_net_value_inr": round(expected_net_val, 2),
            "stop_reason": None,
            "arm_scores": arm_scores,
        }
        result["explanation"] = generate_decision_explanation(transaction, result)

        if self.audit_logger:
            self.audit_logger.log(
                transaction_id=tx_id,
                timestamp=transaction.get("simulated_day", 1),
                context_vector=transaction,
                arm_chosen=recommended_delay,
                expected_value=expected_net_val,
                actual_outcome=0,
                amount_recovered=0.0,
                reward=0.0,
            )

        return result


def get_retry_decision(
    transaction: Dict[str, Any],
    policy: Optional[BasePolicy] = None,
    attempt_number: int = 1,
    previous_success: bool = False,
    audit_logger: Optional[AuditLogger] = None,
) -> Dict[str, Any]:
    """
    Convenience function wrapper for get_retry_decision.
    """
    service = DecisionService(policy=policy, audit_logger=audit_logger)
    return service.get_retry_decision(
        transaction=transaction,
        attempt_number=attempt_number,
        previous_success=previous_success,
    )
