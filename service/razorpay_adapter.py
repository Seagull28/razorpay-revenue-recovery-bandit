"""
razorpay_adapter.py
Translates a real Razorpay payment.failed webhook payload into RecoverFlow's
internal transaction-context dict format.

Real Razorpay webhook shape (top-level):
{
  "entity": "event",
  "account_id": "acc_...",
  "event": "payment.failed",
  "contains": ["payment"],
  "payload": {
    "payment": {
      "entity": {
        "id": "pay_...",
        "amount": 500000,          # in paise (INR * 100)
        "currency": "INR",
        "status": "failed",
        "order_id": "order_...",
        "method": "card",          # "card" | "upi" | "netbanking" | "wallet"
        "card": {"network": "Visa", ...},   # present only if method == "card"
        "bank": "HDFC",             # present for netbanking/some card txns
        "vpa": "user@okhdfcbank",   # present only if method == "upi"
        "error_code": "BAD_REQUEST_ERROR",
        "error_description": "...",
        "error_reason": "insufficient_funds",  # this is what we map to failure_code
        "created_at": 1735689600
      }
    }
  }
}
"""
from typing import Any, Dict
from datetime import datetime, timezone

# Razorpay error_reason -> RecoverFlow internal failure_code vocabulary.
# Extend this mapping if new error_reason values appear in production traffic —
# unmapped reasons fall back to "network_timeout" as a conservative default
# (retryable), NOT "card_expired" (a hard-stop) — never default to a hard-stop
# on an unrecognized reason, that's a safety-critical choice.
RAZORPAY_ERROR_REASON_MAP: Dict[str, str] = {
    "insufficient_funds": "insufficient_funds",
    "expired_card": "card_expired",
    "card_expired": "card_expired",
    "issuer_timeout": "network_timeout",
    "gateway_timeout": "network_timeout",
    "do_not_honor": "do_not_honor",
    "stolen_card": "stolen_card",
    "lost_card": "stolen_card",
    "restricted_card": "stolen_card",
}

RAZORPAY_METHOD_MAP: Dict[str, str] = {
    "card": "card",
    "upi": "upi",
    "netbanking": "netbanking",
    "wallet": "netbanking",  # no dedicated wallet channel in V2's action space; closest fallback
}


class RazorpayAdapterError(ValueError):
    """Raised when a webhook payload is malformed or missing required fields."""


def parse_razorpay_webhook(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a raw Razorpay payment.failed webhook payload into RecoverFlow's
    internal tx_context dict. Raises RazorpayAdapterError on malformed input
    rather than silently guessing defaults for required fields (amount,
    transaction id, failure reason) — silent defaults on money-relevant fields
    are a correctness risk, not a convenience.
    """
    if not isinstance(raw_payload, dict):
        raise RazorpayAdapterError("Webhook payload must be a JSON object.")

    if raw_payload.get("event") != "payment.failed":
        raise RazorpayAdapterError(
            f"Expected event 'payment.failed', got '{raw_payload.get('event')}'"
        )

    try:
        payload_sec = raw_payload["payload"]
        if not isinstance(payload_sec, dict):
            raise TypeError("payload section must be a dictionary")
        payment_sec = payload_sec["payment"]
        if not isinstance(payment_sec, dict):
            raise TypeError("payment section must be a dictionary")
        payment = payment_sec["entity"]
        if not isinstance(payment, dict):
            raise TypeError("payment.entity must be a dictionary")
    except (KeyError, TypeError) as e:
        raise RazorpayAdapterError(f"Malformed payload: missing payload.payment.entity ({e})")

    required = ["id", "amount", "method"]
    missing = [f for f in required if f not in payment]
    if missing:
        raise RazorpayAdapterError(f"Missing required payment fields: {missing}")

    razorpay_method = payment["method"]
    source_method = RAZORPAY_METHOD_MAP.get(razorpay_method)
    if source_method is None:
        raise RazorpayAdapterError(f"Unrecognized payment method: '{razorpay_method}'")

    error_reason = payment.get("error_reason", "")
    failure_code = RAZORPAY_ERROR_REASON_MAP.get(error_reason, "network_timeout")

    bank = payment.get("bank") or "HDFC"  # fallback only for cosmetic display, not decision-critical
    network = "VISA"
    if payment.get("card") and isinstance(payment["card"], dict):
        network = str(payment["card"].get("network", "VISA")).upper()

    amount_inr = float(payment["amount"]) / 100.0  # Razorpay amounts are in paise

    created_at_unix = payment.get("created_at")
    if created_at_unix:
        dt = datetime.fromtimestamp(created_at_unix, tz=timezone.utc)
        simulated_day = min(dt.day, 30)
    else:
        simulated_day = 15

    return {
        "transaction_id": payment["id"],
        "amount": amount_inr,
        "source_method": source_method,
        "failure_code": failure_code,
        "bank": bank,
        "network": network,
        "merchant_tier": "TIER_1",  # not present in Razorpay payload; fixed default, documented as such
        "attempt_number": 1,        # webhook doesn't carry prior attempt count; caller may override via query param
        "simulated_day": simulated_day,
    }
