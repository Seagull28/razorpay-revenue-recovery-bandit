"""
logger.py
Audit Logger implementing the Section 7 Audit Log Schema from the Design Doc.
Logs every retry decision for full explainability and evaluation.
"""

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class AuditRecord:
    """
    Schema conforming strictly to Section 7 of Design Doc:
    transaction_id, timestamp, context_vector, arm_chosen,
    expected_value, actual_outcome, amount_recovered, reward
    """
    transaction_id: str
    timestamp: Any
    context_vector: Dict[str, Any]
    arm_chosen: str
    expected_value: Optional[float]
    actual_outcome: int  # 1 for success, 0 for failure
    amount_recovered: float
    reward: float


class AuditLogger:
    """
    In-memory and exportable audit trail of all scheduling decisions and outcomes.
    """

    def __init__(self):
        self.records: List[AuditRecord] = []

    def log(
        self,
        transaction_id: str,
        timestamp: Any,
        context_vector: Dict[str, Any],
        arm_chosen: str,
        expected_value: Optional[float],
        actual_outcome: int,
        amount_recovered: float,
        reward: float,
    ) -> AuditRecord:
        """Appends a new decision record conforming to the Section 7 schema."""
        record = AuditRecord(
            transaction_id=str(transaction_id),
            timestamp=timestamp,
            context_vector=dict(context_vector),
            arm_chosen=str(arm_chosen),
            expected_value=expected_value,
            actual_outcome=int(actual_outcome),
            amount_recovered=float(amount_recovered),
            reward=float(reward),
        )
        self.records.append(record)
        return record

    def to_records(self) -> List[Dict[str, Any]]:
        """Returns the audit log as a list of dictionaries."""
        return [asdict(r) for r in self.records]

    def to_flat_records(self) -> List[Dict[str, Any]]:
        """Returns records with context features flattened to top-level keys."""
        flat_list = []
        for r in self.records:
            d = asdict(r)
            ctx = r.context_vector
            d["failure_code"] = ctx.get("failure_code")
            d["bank"] = ctx.get("bank")
            d["network"] = ctx.get("network")
            d["retry_attempt_number"] = ctx.get("retry_attempt_number")
            d["day_of_month_bucket"] = ctx.get("day_of_month_bucket")
            d["customer_prior_success_count"] = ctx.get("customer_prior_success_count")
            d["customer_prior_failures_this_cycle"] = ctx.get("customer_prior_failures_this_cycle")
            d["simulated_day"] = ctx.get("simulated_day")
            flat_list.append(d)
        return flat_list

    def to_dataframe(self):
        """Converts audit log to pandas/polars DataFrame if available, else returns flat records."""
        try:
            import pandas as pd
            return pd.DataFrame(self.to_flat_records())
        except ImportError:
            try:
                import polars as pl
                return pl.DataFrame(self.to_flat_records())
            except ImportError:
                return self.to_flat_records()

    def compute_summary_metrics(self) -> Dict[str, Any]:
        """
        Computes aggregated summary performance metrics from the audit log:
        - Total initial transactions processed
        - Total retry attempts made
        - Overall recovery rate (%)
        - Total revenue recovered (INR)
        - Total retry attempt cost incurred (INR)
        - Net revenue (INR)
        - Per-failure-code breakdown
        - Per-bank breakdown
        """
        if not self.records:
            return {
                "total_transactions": 0,
                "total_attempts": 0,
                "recovered_transactions": 0,
                "recovery_rate_pct": 0.0,
                "total_revenue_recovered": 0.0,
                "total_retry_cost": 0.0,
                "net_revenue": 0.0,
                "avg_net_revenue_per_tx": 0.0,
                "by_failure_code": {},
                "by_bank": {},
            }

        # Aggregate by transaction_id
        tx_stats = {}
        total_attempts = len(self.records)
        total_net_revenue = 0.0

        for r in self.records:
            tx_id = r.transaction_id
            total_net_revenue += r.reward
            ctx = r.context_vector

            if tx_id not in tx_stats:
                tx_stats[tx_id] = {
                    "recovered": bool(r.actual_outcome == 1),
                    "amount_recovered": r.amount_recovered,
                    "attempts": 1,
                    "failure_code": ctx.get("failure_code", "unknown"),
                    "bank": ctx.get("bank", "unknown"),
                    "network": ctx.get("network", "unknown"),
                }
            else:
                if r.actual_outcome == 1:
                    tx_stats[tx_id]["recovered"] = True
                    tx_stats[tx_id]["amount_recovered"] = max(
                        tx_stats[tx_id]["amount_recovered"], r.amount_recovered
                    )
                tx_stats[tx_id]["attempts"] += 1

        total_tx = len(tx_stats)
        recovered_tx = sum(1 for s in tx_stats.values() if s["recovered"])
        recovery_rate_pct = (recovered_tx / total_tx * 100.0) if total_tx > 0 else 0.0
        total_revenue_recovered = sum(s["amount_recovered"] for s in tx_stats.values())
        total_retry_cost = total_revenue_recovered - total_net_revenue

        # Per failure code breakdown
        code_groups = defaultdict(lambda: {"total": 0, "recovered": 0, "revenue": 0.0})
        for s in tx_stats.values():
            code = s["failure_code"]
            code_groups[code]["total"] += 1
            if s["recovered"]:
                code_groups[code]["recovered"] += 1
                code_groups[code]["revenue"] += s["amount_recovered"]

        by_failure_code = {}
        for code, g in code_groups.items():
            by_failure_code[code] = {
                "total_transactions": g["total"],
                "recovered_transactions": g["recovered"],
                "recovery_rate_pct": round((g["recovered"] / g["total"] * 100.0), 2) if g["total"] > 0 else 0.0,
                "total_recovered_inr": round(g["revenue"], 2),
            }

        # Per bank breakdown
        bank_groups = defaultdict(lambda: {"total": 0, "recovered": 0, "revenue": 0.0})
        for s in tx_stats.values():
            b = s["bank"]
            bank_groups[b]["total"] += 1
            if s["recovered"]:
                bank_groups[b]["recovered"] += 1
                bank_groups[b]["revenue"] += s["amount_recovered"]

        by_bank = {}
        for b, g in bank_groups.items():
            by_bank[b] = {
                "total_transactions": g["total"],
                "recovered_transactions": g["recovered"],
                "recovery_rate_pct": round((g["recovered"] / g["total"] * 100.0), 2) if g["total"] > 0 else 0.0,
                "total_recovered_inr": round(g["revenue"], 2),
            }

        return {
            "total_transactions": total_tx,
            "total_attempts": total_attempts,
            "recovered_transactions": recovered_tx,
            "recovery_rate_pct": round(recovery_rate_pct, 2),
            "total_revenue_recovered": round(total_revenue_recovered, 2),
            "total_retry_cost": round(total_retry_cost, 2),
            "net_revenue": round(total_net_revenue, 2),
            "avg_net_revenue_per_tx": round(total_net_revenue / total_tx, 2) if total_tx > 0 else 0.0,
            "by_failure_code": by_failure_code,
            "by_bank": by_bank,
        }

    def clear(self) -> None:
        """Clears all audit records."""
        self.records.clear()

    def get_summary(self) -> Dict[str, Any]:
        """Alias for compute_summary_metrics."""
        return self.compute_summary_metrics()
