"""
recovery_insights.py
Merchant Recovery Insights & Opportunity Scoring Engine for RecoverFlow.
Aggregates recovery decisions across observable dimensions (failure_code, bank, network,
amount_bucket, day_of_month_bucket) to compute Recovery Opportunity Scores (0-100)
and segment risk classifications. Uses ONLY observable simulation data.
"""

from typing import Any, Dict, List, Optional
from bandit_retry_scheduler.core.strategy import RETRY_ARM_TO_STRATEGY, STRATEGY_METADATA

DEMO_DISCLOSURE = (
    "DEMO SAMPLE DATA (Dashboard Empty State) — Synthetic simulation data demonstration only."
)

EVAL_DISCLOSURE = (
    "Synthetic simulation insight — derived dynamically from Phase 3 evaluation benchmark records."
)


def calculate_opportunity_score(
    transaction_count: int,
    recovery_rate: float,
    mean_net_value_inr: float,
) -> float:
    """
    Calculates normalized Recovery Opportunity Score (0 to 100).
    Opportunity Score = min(100, volume_factor * recovery_rate * value_factor)
    Represents synthetic prioritization for where retry optimization has greatest potential impact.
    """
    if transaction_count <= 0:
        return 0.0

    vol_factor = min(1.0, transaction_count / 100.0)
    rate_factor = max(0.0, min(1.0, recovery_rate))
    val_factor = min(1.0, max(0.0, mean_net_value_inr) / 500.0)

    score = vol_factor * (0.40 * rate_factor + 0.60 * val_factor) * 100.0
    return round(min(100.0, max(0.0, score)), 1)


def generate_merchant_recovery_insights(
    eval_records: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Aggregates evaluation decision records across context dimensions.
    Returns structured segment insights, top opportunity leaderboard, and synthetic disclosure.
    When eval_records is provided, all metrics, top segments, and strategies are derived dynamically.
    """
    if not eval_records:
        # Fallback demonstration data for initial dashboard render before live simulation
        segments = [
            {
                "dimension": "failure_code",
                "segment": "insufficient_funds",
                "transaction_count": 1240,
                "recovery_rate": 0.64,
                "recommended_strategy": "PATIENT_RECOVERY (3d)",
                "opportunity_score": 84.2,
                "risk_level": "MEDIUM",
                "summary": "High-volume salary-cycle decline code with strong recovery odds at 3d delay window.",
            },
            {
                "dimension": "failure_code",
                "segment": "issuer_timeout",
                "transaction_count": 860,
                "recovery_rate": 0.78,
                "recommended_strategy": "IMMEDIATE_RECOVERY (1hr)",
                "opportunity_score": 91.5,
                "risk_level": "LOW",
                "summary": "Transient gateway congestion context with rapid recovery potential at 1hr delay window.",
            },
            {
                "dimension": "failure_code",
                "segment": "do_not_honor",
                "transaction_count": 520,
                "recovery_rate": 0.32,
                "recommended_strategy": "LAST_CHANCE_RECOVERY (7d)",
                "opportunity_score": 42.0,
                "risk_level": "HIGH",
                "summary": "High-friction bank restriction code; requires extended 7d retry window or manual outreach.",
            },
            {
                "dimension": "day_of_month_bucket",
                "segment": "early (Days 1-5)",
                "transaction_count": 1450,
                "recovery_rate": 0.72,
                "recommended_strategy": "BALANCED_RETRY (1d)",
                "opportunity_score": 88.0,
                "risk_level": "LOW",
                "summary": "Month-beginning salary mandates processing window with high overall recovery rate.",
            },
        ]
        
        return {
            "overall_recovery_rate": 0.612,
            "total_transactions_analyzed": 4070,
            "highest_opportunity_segment": "issuer_timeout (Opportunity Score: 91.5)",
            "highest_risk_segment": "do_not_honor (Risk Level: HIGH)",
            "best_performing_strategy": "PATIENT_RECOVERY (3d)",
            "segments": segments,
            "synthetic_data_notice": DEMO_DISCLOSURE,
            "is_demo_fallback": True,
        }

    # Aggregate dynamically when actual evaluation records are provided
    by_code: Dict[str, List[Dict[str, Any]]] = {}
    strategy_counts: Dict[str, int] = {}

    for r in eval_records:
        # Extract failure code from record top-level or raw decision or context
        code = r.get("failure_code")
        if not code and "raw_decision" in r:
            code = r.get("raw_decision", {}).get("transaction", {}).get("failure_code")
        if not code:
            code = "generic_decline"

        by_code.setdefault(code, []).append(r)

        # Track recommended strategies
        rec_strat = r.get("recommendation", {}).get("strategy")
        rec_delay = r.get("recommendation", {}).get("retry_delay")
        if rec_strat and rec_delay:
            key = f"{rec_strat} ({rec_delay})"
            strategy_counts[key] = strategy_counts.get(key, 0) + 1

    segments = []
    for code, records in by_code.items():
        count = len(records)
        succ = sum(1 for rec in records if rec.get("should_retry", False))
        rate = succ / count if count > 0 else 0.0
        avg_val = sum(rec.get("expected_net_value_inr", 0.0) for rec in records) / count if count > 0 else 0.0
        opp_score = calculate_opportunity_score(count, rate, avg_val)

        risk = "LOW" if rate >= 0.60 else ("MEDIUM" if rate >= 0.35 else "HIGH")

        # Dynamic most frequent strategy per segment
        seg_strats: Dict[str, int] = {}
        for rec in records:
            st = rec.get("recommendation", {}).get("strategy")
            dl = rec.get("recommendation", {}).get("retry_delay")
            if st and dl:
                k = f"{st} ({dl})"
                seg_strats[k] = seg_strats.get(k, 0) + 1
        
        top_seg_strat = max(seg_strats.items(), key=lambda x: x[1])[0] if seg_strats else "N/A"

        segments.append({
            "dimension": "failure_code",
            "segment": code,
            "transaction_count": count,
            "recovery_rate": round(rate, 3),
            "recommended_strategy": top_seg_strat,
            "opportunity_score": opp_score,
            "risk_level": risk,
            "summary": f"Evaluated segment '{code}' across {count} records (retry rate: {round(rate*100,1)}%).",
        })

    segments.sort(key=lambda x: x["opportunity_score"], reverse=True)
    top_seg = f"{segments[0]['segment']} (Opportunity Score: {segments[0]['opportunity_score']})" if segments else "N/A"
    high_risk_seg = next((f"{s['segment']} (Risk Level: HIGH)" for s in segments if s["risk_level"] == "HIGH"), "None")
    
    top_overall_strategy = max(strategy_counts.items(), key=lambda x: x[1])[0] if strategy_counts else "N/A"

    return {
        "overall_recovery_rate": round(sum(s["recovery_rate"] for s in segments) / len(segments), 3) if segments else 0.0,
        "total_transactions_analyzed": len(eval_records),
        "highest_opportunity_segment": top_seg,
        "highest_risk_segment": high_risk_seg,
        "best_performing_strategy": top_overall_strategy,
        "segments": segments,
        "synthetic_data_notice": EVAL_DISCLOSURE,
        "is_demo_fallback": False,
    }
