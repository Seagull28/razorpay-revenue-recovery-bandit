"""
explainability.py
Explainable decision output generator for RecoverFlow API decisions.
Translates technical LinUCB arm scores, expected net revenue, and stopping rules
into clear, human-readable business explanations.
"""

from typing import Any, Dict, Optional


def generate_decision_explanation(
    transaction: Dict[str, Any],
    decision: Dict[str, Any],
) -> str:
    """
    Generates a human-readable business explanation from a decision dictionary.

    Parameters:
    -----------
    transaction: dict containing transaction details (amount, failure_code, bank, etc.)
    decision: dict returned by get_retry_decision()

    Returns:
    --------
    Human-readable explanation string.
    """
    tx_id = transaction.get("transaction_id", "unknown_tx")
    code = transaction.get("failure_code", "unknown")
    bank = transaction.get("bank", "unknown")
    amount = float(transaction.get("amount", 1500.0))
    should_retry = decision.get("should_retry", False)
    stop_reason = decision.get("stop_reason")
    recommended_delay = decision.get("recommended_delay")
    expected_net_value = decision.get("expected_net_value_inr", 0.0)
    arm_scores = decision.get("arm_scores", {})

    if not should_retry:
        if stop_reason == "hard_stop_card_expired":
            return (
                f"Retries halted for transaction {tx_id} ({code} on {bank}): Card Expired - Hard Stop. "
                f"Payment retries are disabled after attempt 1 for expired cards as recovery probability is 0%."
            )
        elif stop_reason and "max_attempts" in stop_reason:
            return (
                f"Retries halted for transaction {tx_id} ({code} on {bank}): Max attempts cap reached. "
                f"No further retry attempts are permitted."
            )
        elif stop_reason and ("negative_ev" in stop_reason or "ev_stopping" in stop_reason or "zero_ev" in stop_reason):
            best_arm = max(arm_scores, key=lambda a: arm_scores[a].get("theta_dot_x", -999)) if arm_scores else "N/A"
            best_ev = arm_scores.get(best_arm, {}).get("theta_dot_x", 0.0) if arm_scores else 0.0
            return (
                f"Retries halted for transaction {tx_id} ({code} on {bank}): Expected net revenue across all delay arms "
                f"is <= INR 0.00 (highest candidate arm '{best_arm}' has expected net value INR {best_ev:,.2f} after INR 10 retry cost)."
            )
        else:
            return (
                f"Retries halted for transaction {tx_id} ({code} on {bank}): Stop rule triggered ({stop_reason})."
            )

    # Retry recommended
    chosen_details = arm_scores.get(recommended_delay, {})
    theta_dot_x = chosen_details.get("theta_dot_x", expected_net_value)
    
    # Calculate implicit recovery probability P = (EV + retry_cost) / amount
    implied_prob = (theta_dot_x + 10.0) / amount if amount > 0 else 0.0
    implied_prob_pct = max(0.0, min(100.0, implied_prob * 100.0))

    # Formulate alternatives comparison text
    alt_parts = []
    for arm, scores in arm_scores.items():
        if arm != recommended_delay:
            ev = scores.get("theta_dot_x", 0.0)
            alt_parts.append(f"{arm} (EV: INR {ev:,.2f})")
    alt_text = ", ".join(alt_parts)

    # Check if this is a marginal case (very low expected net value or near-zero recovery probability)
    is_marginal = (theta_dot_x <= 25.0 or implied_prob_pct <= 3.0)
    marginal_prefix = "Marginal case: model believes this retry is barely worth attempting — " if is_marginal else ""

    explanation = (
        f"{marginal_prefix}Recommended {recommended_delay} delay for transaction {tx_id} (amount: INR {amount:,.2f}, {code} on {bank}): "
        f"estimated {implied_prob_pct:.1f}% recovery probability on this context, yielding expected net value of "
        f"INR {theta_dot_x:,.2f} after INR 10 retry cost. Alternative arms considered: {alt_text}."
    )
    return explanation
