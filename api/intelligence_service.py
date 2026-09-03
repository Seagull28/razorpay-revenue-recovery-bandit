"""
intelligence_service.py
Recovery Intelligence API Service for RecoverFlow.
Enriches raw get_retry_decision() recommendations with strategy classification,
score-gap confidence metrics, decision stability, risk profiling, strategy mode selection,
and synthetic simulation disclosures.
"""

from typing import Any, Dict, Optional
from bandit_retry_scheduler.api.decision_service import DecisionService
from bandit_retry_scheduler.core.strategy import (
    get_strategy_metadata,
    calculate_decision_confidence,
    classify_decision_stability,
    get_alternative_strategies,
)
from bandit_retry_scheduler.core.risk import (
    evaluate_risk_aware_recommendation,
    compute_risk_profile,
    StrategyMode,
)
from bandit_retry_scheduler.policies.base import BasePolicy
from bandit_retry_scheduler.audit.logger import AuditLogger


SIMULATION_DISCLOSURE = (
    "This recommendation is generated using a synthetic payment recovery simulation "
    "and is not based on real merchant payment data."
)


def get_recovery_intelligence(
    transaction: Dict[str, Any],
    strategy_mode: str = "BALANCED",
    policy: Optional[BasePolicy] = None,
    attempt_number: int = 1,
    previous_success: bool = False,
    audit_logger: Optional[AuditLogger] = None,
) -> Dict[str, Any]:
    """
    Primary API endpoint for Phase 3 Recovery Intelligence.
    Integrates DecisionService with Strategy Engine and Risk Engine.
    Backward-compatible with existing get_retry_decision() data structures.
    """
    decision_service = DecisionService(policy=policy, audit_logger=audit_logger)
    raw_decision = decision_service.get_retry_decision(
        transaction=transaction,
        attempt_number=attempt_number,
        previous_success=previous_success,
    )

    tx_id = transaction.get("transaction_id", "unknown_tx")
    arm_scores = raw_decision.get("arm_scores", {})
    mode = strategy_mode.upper() if strategy_mode else StrategyMode.BALANCED.value

    # Calculate confidence and stability
    confidence_score, confidence_interp = calculate_decision_confidence(arm_scores)
    stability = classify_decision_stability(confidence_score)

    if not raw_decision.get("should_retry", False):
        risk_profile = compute_risk_profile(transaction, arm_scores, attempt_number)
        return {
            "transaction_id": tx_id,
            "strategy_mode": mode,
            "should_retry": False,
            "recommendation": {
                "retry_delay": None,
                "strategy": None,
                "title": "No Retry Recommended",
                "description": f"Retries halted: {raw_decision.get('stop_reason', 'Eligibility or Expected Value Stop')}",
            },
            "expected_net_value_inr": 0.0,
            "confidence": {
                "score": confidence_score,
                "interpretation": confidence_interp,
            },
            "decision_stability": stability,
            "risk_profile": risk_profile.to_dict(),
            "alternatives": get_alternative_strategies(arm_scores, selected_arm=""),
            "explanation": raw_decision.get("explanation", ""),
            "simulation_disclosure": SIMULATION_DISCLOSURE,
            "raw_decision": raw_decision,
        }

    # Evaluate risk-aware recommendation
    raw_arm = raw_decision["recommended_delay"]
    recommended_arm, risk_profile, risk_meta = evaluate_risk_aware_recommendation(
        arm_scores=arm_scores,
        raw_selected_arm=raw_arm,
        transaction=transaction,
        strategy_mode=mode,
        attempt_number=attempt_number,
    )

    strategy_meta = get_strategy_metadata(recommended_arm)
    alternatives = get_alternative_strategies(arm_scores, selected_arm=recommended_arm)

    # Enrich explanation
    base_explanation = raw_decision.get("explanation", "")
    mode_note = f" (Selected under {mode} strategy mode)." if mode != StrategyMode.MAXIMIZE_RECOVERY.value else ""
    enriched_explanation = (
        f"{base_explanation} Recommended Strategy: '{strategy_meta['title']}' ({recommended_arm}) "
        f"with {stability} stability and {risk_profile.risk_level} risk profile{mode_note}"
    )

    return {
        "transaction_id": tx_id,
        "strategy_mode": mode,
        "should_retry": True,
        "recommendation": {
            "retry_delay": recommended_arm,
            "strategy": strategy_meta["strategy"],
            "title": strategy_meta["title"],
            "description": strategy_meta["description"],
        },
        "expected_net_value_inr": raw_decision.get("expected_net_value_inr", 0.0),
        "confidence": {
            "score": confidence_score,
            "interpretation": confidence_interp,
        },
        "decision_stability": stability,
        "risk_profile": risk_profile.to_dict(),
        "raw_policy_arm": raw_arm,
        "final_recommended_arm": recommended_arm,
        "alternatives": alternatives,
        "explanation": enriched_explanation,
        "simulation_disclosure": SIMULATION_DISCLOSURE,
        "raw_decision": raw_decision,
    }
