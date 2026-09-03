"""
strategy.py
Recovery Strategy Intelligence Engine for RecoverFlow.
Maps raw retry arm choices into human-readable recovery strategies, calculates
scale-aware decision confidence based on relative score separation, classifies decision stability,
and ranks alternative retry strategies.
"""

from enum import Enum
from typing import Any, Dict, List, Tuple

class StrategyCategory(str, Enum):
    IMMEDIATE_RECOVERY = "IMMEDIATE_RECOVERY"
    FAST_RETRY = "FAST_RETRY"
    BALANCED_RETRY = "BALANCED_RETRY"
    PATIENT_RECOVERY = "PATIENT_RECOVERY"
    LAST_CHANCE_RECOVERY = "LAST_CHANCE_RECOVERY"


# Configurable mapping from retry delay arms to strategy categories
RETRY_ARM_TO_STRATEGY: Dict[str, StrategyCategory] = {
    "1hr": StrategyCategory.IMMEDIATE_RECOVERY,
    "6hr": StrategyCategory.FAST_RETRY,
    "1d": StrategyCategory.BALANCED_RETRY,
    "3d": StrategyCategory.PATIENT_RECOVERY,
    "7d": StrategyCategory.LAST_CHANCE_RECOVERY,
}

# Deterministic default arm preference ordering for explicit tie-breaking
DETERMINISTIC_ARM_ORDER: List[str] = ["3d", "1d", "6hr", "1hr", "7d"]

STRATEGY_METADATA: Dict[StrategyCategory, Dict[str, str]] = {
    StrategyCategory.IMMEDIATE_RECOVERY: {
        "title": "Immediate Recovery",
        "description": "Retries quickly within 1 hour to capture transient gateway timeouts while customer intent is high.",
    },
    StrategyCategory.FAST_RETRY: {
        "title": "Fast Retry",
        "description": "Retries within 6 hours to allow short-term bank network congestion or temporary system holds to clear.",
    },
    StrategyCategory.BALANCED_RETRY: {
        "title": "Balanced Retry",
        "description": "Retries after 1 day to balance recovery odds against customer account updates and daily processing cycles.",
    },
    StrategyCategory.PATIENT_RECOVERY: {
        "title": "Patient Recovery",
        "description": "Allows 3 days for customer funds or salary credit cycles to replenish before retrying.",
    },
    StrategyCategory.LAST_CHANCE_RECOVERY: {
        "title": "Last Chance Recovery",
        "description": "Waits 7 days as a final extended window for high-friction decline codes before exhausting retries.",
    },
}

# Scale-Aware Stability Threshold Constants (confidence score bounds 0.0 to 1.0)
STABLE_CONFIDENCE_THRESHOLD: float = 0.50
MODERATE_CONFIDENCE_THRESHOLD: float = 0.20


def get_strategy_category(retry_delay: str) -> StrategyCategory:
    """Returns the StrategyCategory for a given retry delay arm."""
    return RETRY_ARM_TO_STRATEGY.get(retry_delay, StrategyCategory.BALANCED_RETRY)


def get_strategy_metadata(retry_delay: str) -> Dict[str, str]:
    """Returns human-readable title and description for a retry delay arm."""
    category = get_strategy_category(retry_delay)
    meta = STRATEGY_METADATA.get(category, {}).copy()
    meta["strategy"] = category.value
    meta["retry_delay"] = retry_delay
    return meta


def calculate_decision_confidence(arm_scores: Dict[str, Any]) -> Tuple[float, str]:
    """
    Calculates scale-aware decision confidence from relative score gap between top two candidate arms.
    Confidence represents relative score separation between candidate retry windows (0.0 to 1.0),
    NOT guaranteed payment recovery probability. Non-biased across transaction amount scales.
    """
    if not arm_scores:
        return 0.50, "Relative separation between leading retry candidates"

    # Extract score values
    scores = []
    for arm, details in arm_scores.items():
        if isinstance(details, dict):
            val = float(details.get("score", details.get("ucb_score", 0.0)))
        elif isinstance(details, (int, float)):
            val = float(details)
        else:
            val = 0.0
        scores.append(val)

    if len(scores) < 2:
        return 1.0, "Single candidate arm evaluated"

    scores.sort(reverse=True)
    top_score = scores[0]
    second_score = scores[1]

    # Raw score gap calculation
    raw_gap = top_score - second_score
    
    # Scale-aware relative gap: relative to top score magnitude or cost floor (50.0 INR)
    scale = max(abs(top_score), 50.0)
    relative_gap = raw_gap / scale

    # Normalize: 25% relative gap yields 100% confidence
    confidence = min(1.0, max(0.0, relative_gap / 0.25))
    confidence_rounded = round(float(confidence), 4)
    
    interpretation = "Relative separation between leading retry candidates"
    return confidence_rounded, interpretation


def classify_decision_stability(confidence_score: float, score_gap: float = None) -> str:
    """
    Classifies decision stability based on confidence score or relative score gap.
    Returns: 'STABLE', 'MODERATELY_STABLE', or 'UNSTABLE'.
    """
    if confidence_score >= STABLE_CONFIDENCE_THRESHOLD:
        return "STABLE"
    elif confidence_score >= MODERATE_CONFIDENCE_THRESHOLD:
        return "MODERATELY_STABLE"
    else:
        return "UNSTABLE"


def get_alternative_strategies(arm_scores: Dict[str, Any], selected_arm: str) -> List[Dict[str, Any]]:
    """
    Returns ranked alternative candidate retry strategies sorted by policy score.
    The selected arm will be rank 1. Deterministic tie-breaking applied.
    """
    if not arm_scores:
        return []

    parsed = []
    for arm, details in arm_scores.items():
        if isinstance(details, dict):
            score = float(details.get("score", details.get("ucb_score", 0.0)))
        elif isinstance(details, (int, float)):
            score = float(details)
        else:
            score = 0.0
        
        category = get_strategy_category(arm)
        meta = STRATEGY_METADATA.get(category, {})
        
        # Deterministic sorting key
        arm_idx = DETERMINISTIC_ARM_ORDER.index(arm) if arm in DETERMINISTIC_ARM_ORDER else 99
        parsed.append({
            "retry_delay": arm,
            "strategy": category.value,
            "title": meta.get("title", arm),
            "score": round(score, 4),
            "is_selected": (arm == selected_arm),
            "_sort_key": (round(score, 2), -arm_idx),
        })

    # Sort descending by score, tie-broken by deterministic arm preference order
    parsed.sort(key=lambda x: x["_sort_key"], reverse=True)

    ranked = []
    for idx, item in enumerate(parsed, start=1):
        clean_item = dict(item)
        clean_item.pop("_sort_key", None)
        clean_item["rank"] = idx
        ranked.append(clean_item)

    return ranked
