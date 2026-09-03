"""
RecoverFlow API package.
Exposes eligibility checks, decision service, explainability generator, and audit trail.
"""

from bandit_retry_scheduler.api.eligibility import check_eligibility, EligibilityGate
from bandit_retry_scheduler.api.explainability import generate_decision_explanation
from bandit_retry_scheduler.api.decision_service import get_retry_decision, DecisionService
from bandit_retry_scheduler.api.audit_service import AuditService
from bandit_retry_scheduler.api.action_executor import execute_retry_action
from bandit_retry_scheduler.api.feedback_loop import process_outcome_and_update

__all__ = [
    "check_eligibility",
    "EligibilityGate",
    "generate_decision_explanation",
    "get_retry_decision",
    "DecisionService",
    "AuditService",
    "execute_retry_action",
    "process_outcome_and_update",
]
