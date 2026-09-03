"""
audit_service.py
Audit Trail API service for RecoverFlow.
Exposes the existing AuditLogger to query decision history and audit trails.
"""

from typing import Any, Dict, List, Optional
from bandit_retry_scheduler.audit.logger import AuditLogger


class AuditService:
    """
    Service wrapping an AuditLogger instance to query decision histories.
    """

    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self.audit_logger = audit_logger if audit_logger is not None else AuditLogger()

    def get_transaction_history(self, transaction_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all logged decisions for a specific transaction_id.
        """
        history = []
        for record in self.audit_logger.records:
            if getattr(record, "transaction_id", None) == transaction_id:
                history.append(record)
        return history

    def get_all_records(self) -> List[Dict[str, Any]]:
        """
        Returns all logged audit records.
        """
        return self.audit_logger.records

    def get_audit_summary(self) -> Dict[str, Any]:
        """
        Returns summary metrics from the audit logger.
        """
        return self.audit_logger.get_summary()
