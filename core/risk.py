"""
risk.py
Risk-Aware Recovery Intelligence Engine for RecoverFlow.
Provides strategy modes (MAXIMIZE_RECOVERY, BALANCED, CONSERVATIVE) and risk profiling
using strictly observable transaction context and decision score separation.
Does NOT modify LinUCBPolicy, ContextEncoder, or simulator ground_truth.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple
from bandit_retry_scheduler.core.strategy import (
    calculate_decision_confidence,
    classify_decision_stability,
    DETERMINISTIC_ARM_ORDER,
)


class StrategyMode(str, Enum):
    MAXIMIZE_RECOVERY = "MAXIMIZE_RECOVERY"
    BALANCED = "BALANCED"
    CONSERVATIVE = "CONSERVATIVE"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class RiskProfile:
    risk_score: float
    risk_level: str
    risk_factors: List[str] = field(default_factory=list)
    decision_stability: str = "STABLE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_score": round(self.risk_score, 2),
            "risk_level": self.risk_level,
            "risk_factors": self.risk_factors,
            "decision_stability": self.decision_stability,
        }


HIGH_RISK_FAILURE_CODES = {"do_not_honor", "card_expired"}
MEDIUM_RISK_FAILURE_CODES = {"insufficient_funds", "generic_decline"}

# Normalized dimensionless arm timing friction profile R_a in [0.0, 1.0]
ARM_RISK_PROFILE: Dict[str, float] = {
    "3d": 0.10,  # Patient replenish window — lowest timing friction
    "1d": 0.25,  # Balanced daily processing window
    "6hr": 0.45, # Intraday retry — moderate congestion/timing friction
    "1hr": 0.70, # Immediate retry — high risk of retrying before bank/customer state changes
    "7d": 0.85,  # Extended 7-day window — high opportunity-cost & customer churn risk
}


def compute_risk_profile(
    transaction: Dict[str, Any],
    arm_scores: Dict[str, Any],
    attempt_number: int = 1,
) -> RiskProfile:
    """
    Computes a transparent risk profile using strictly observable information.
    Zero access to hidden simulator ground truth or oracle probabilities.
    """
    confidence_score, _ = calculate_decision_confidence(arm_scores)
    stability = classify_decision_stability(confidence_score)
    risk_factors = []

    # 1. Base risk from attempt decay
    attempt_risk = min(0.40, (attempt_number - 1) * 0.15)
    if attempt_number > 1:
        risk_factors.append(f"Repeated retry attempt (Attempt #{attempt_number})")

    # 2. Risk from decision separation / uncertainty
    uncertainty_risk = (1.0 - confidence_score) * 0.35
    if stability in ("UNSTABLE", "MODERATELY_STABLE"):
        risk_factors.append(f"Low score separation between top retry candidates ({stability})")

    # 3. Risk from failure category
    failure_code = transaction.get("failure_code", "").lower()
    code_risk = 0.0
    if failure_code in HIGH_RISK_FAILURE_CODES:
        code_risk = 0.25
        risk_factors.append(f"High-risk decline category ({failure_code})")
    elif failure_code in MEDIUM_RISK_FAILURE_CODES:
        code_risk = 0.15
        risk_factors.append(f"Medium-risk decline category ({failure_code})")

    # Total risk score bounded in [0.0, 1.0]
    total_risk = min(1.0, max(0.0, attempt_risk + uncertainty_risk + code_risk))

    if total_risk < 0.30:
        level = RiskLevel.LOW.value
    elif total_risk < 0.60:
        level = RiskLevel.MEDIUM.value
    else:
        level = RiskLevel.HIGH.value

    return RiskProfile(
        risk_score=total_risk,
        risk_level=level,
        risk_factors=risk_factors,
        decision_stability=stability,
    )


def evaluate_risk_aware_recommendation(
    arm_scores: Dict[str, Any],
    raw_selected_arm: str,
    transaction: Dict[str, Any],
    strategy_mode: str = "BALANCED",
    attempt_number: int = 1,
) -> Tuple[str, RiskProfile, Dict[str, Any]]:
    """
    Evaluates risk-aware strategy recommendations based on merchant preference mode.
    
    Modes & Objective Utility Functions:
    - MAXIMIZE_RECOVERY: U_a = UCB_a (Pure LinUCB bandit utility maximization).
    - BALANCED: U_a = UCB_a - 0.30 * (1 - C) * R_a * max(|UCB_a|, 50.0) (Trade off expected net revenue vs uncertainty-weighted risk).
    - CONSERVATIVE: U_a = UCB_a - 0.70 * (1 - C) * R_a * max(|UCB_a|, 50.0) - (25.0 if arm in ('1hr', '7d') else 0.0).
    
    Uses explicit deterministic tie-breaking:
    1. Adjusted Score (rounded to 2 decimal places)
    2. Raw Policy Score
    3. Deterministic Arm Preference Index (3d -> 1d -> 6hr -> 1hr -> 7d)
    """
    mode = strategy_mode.upper() if strategy_mode else StrategyMode.BALANCED.value
    risk_profile = compute_risk_profile(transaction, arm_scores, attempt_number)

    if not arm_scores:
        return raw_selected_arm, risk_profile, {"mode": mode, "adjusted_scores": {}}

    raw_ucb_scores: Dict[str, float] = {}
    for arm, details in arm_scores.items():
        if isinstance(details, dict):
            ev = float(details.get("score", details.get("ucb_score", 0.0)))
        elif isinstance(details, (int, float)):
            ev = float(details)
        else:
            ev = 0.0
        raw_ucb_scores[arm] = ev

    if mode == StrategyMode.MAXIMIZE_RECOVERY.value:
        return raw_selected_arm, risk_profile, {"mode": mode, "adjusted_scores": raw_ucb_scores, "tie_broken": False}

    confidence_score, _ = calculate_decision_confidence(arm_scores)
    uncertainty_penalty = (1.0 - confidence_score)

    adjusted_scores: Dict[str, float] = {}
    for arm, ev in raw_ucb_scores.items():
        arm_risk = ARM_RISK_PROFILE.get(arm, 0.25)
        score_scale = max(abs(ev), 50.0)

        if mode == StrategyMode.BALANCED.value:
            # Balanced mode: 0.30 multiplier on uncertainty-weighted arm risk
            adj = ev - (0.30 * uncertainty_penalty * arm_risk * score_scale)
        elif mode == StrategyMode.CONSERVATIVE.value:
            # Conservative mode: 0.70 multiplier + fixed extreme window penalty (25 INR)
            extreme_penalty = 25.0 if arm in ("1hr", "7d") else 0.0
            adj = ev - (0.70 * uncertainty_penalty * arm_risk * score_scale) - extreme_penalty
        else:
            adj = ev

        adjusted_scores[arm] = round(adj, 4)

    # Explicit deterministic tie-breaking key:
    # (adjusted_score_round2, raw_ucb_score_round2, -deterministic_arm_index)
    def get_sort_key(arm_name: str) -> Tuple[float, float, int]:
        adj = round(adjusted_scores[arm_name], 2)
        raw = round(raw_ucb_scores.get(arm_name, 0.0), 2)
        idx = DETERMINISTIC_ARM_ORDER.index(arm_name) if arm_name in DETERMINISTIC_ARM_ORDER else 99
        return (adj, raw, -idx)

    best_arm = max(adjusted_scores.keys(), key=get_sort_key)

    # Check if a tie-break was triggered among top candidate scores
    top_adj_scores = sorted([round(v, 2) for v in adjusted_scores.values()], reverse=True)
    tie_broken = (len(top_adj_scores) >= 2 and top_adj_scores[0] == top_adj_scores[1])

    return best_arm, risk_profile, {
        "mode": mode,
        "adjusted_scores": adjusted_scores,
        "original_arm": raw_selected_arm,
        "mode_changed_decision": (best_arm != raw_selected_arm),
        "tie_broken": tie_broken,
    }
