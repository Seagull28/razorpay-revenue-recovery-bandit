"""
test_http_api.py
Unit test suite for service/http_api.py FastAPI endpoints.
Tests health check, Razorpay webhook translation, direct decision endpoint,
card_expired eligibility logic, and stack-trace leak prevention.
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from service.http_api import app

client = TestClient(app)


def test_health_check():
    """GET /health returns 200 and {'status': 'ok'}."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_razorpay_webhook_valid_insufficient_funds():
    """POST /v1/webhooks/razorpay translates payload and returns valid decision."""
    payload = {
        "entity": "event",
        "account_id": "acc_test123",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_funds_123",
                    "amount": 500000,
                    "currency": "INR",
                    "status": "failed",
                    "method": "card",
                    "card": {"network": "Visa"},
                    "bank": "HDFC",
                    "error_reason": "insufficient_funds",
                    "created_at": 1735689600,
                }
            }
        },
    }
    response = client.post("/v1/webhooks/razorpay", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "should_retry" in data
    assert "expected_net_value_inr" in data
    assert "stop_reason" in data


def test_razorpay_webhook_card_expired_returns_halt_or_switch():
    """POST /v1/webhooks/razorpay with expired_card on attempt > 1 enforces hard-stop on card retries."""
    payload = {
        "entity": "event",
        "account_id": "acc_test123",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_expired_123",
                    "amount": 120000,
                    "currency": "INR",
                    "status": "failed",
                    "method": "card",
                    "card": {"network": "Visa"},
                    "bank": "AXIS",
                    "error_reason": "expired_card",
                    "created_at": 1735689600,
                }
            }
        },
    }
    # Pass attempt_number=2 to trigger V2's attempt_number > 1 card_expired eligibility rule
    response = client.post("/v1/webhooks/razorpay?attempt_number=2", json=payload)
    assert response.status_code == 200
    data = response.json()

    if data["should_retry"]:
        assert data["action_chosen"]["target_method"] != "card"
    else:
        assert data["stop_reason"] in ["non_positive_expected_value", "hard_stop_card_expired"]


def test_razorpay_webhook_wrong_event_type_returns_422():
    """POST /v1/webhooks/razorpay with non-payment.failed event returns 422."""
    payload = {"event": "payment.authorized"}
    response = client.post("/v1/webhooks/razorpay", json=payload)
    assert response.status_code == 422
    assert "Expected event 'payment.failed'" in response.json()["detail"]


def test_razorpay_webhook_missing_payment_entity_returns_422():
    """POST /v1/webhooks/razorpay with malformed body missing payment entity returns 422."""
    payload = {"event": "payment.failed", "payload": {}}
    response = client.post("/v1/webhooks/razorpay", json=payload)
    assert response.status_code == 422
    assert "Malformed payload" in response.json()["detail"]


def test_recovery_decide_direct_endpoint():
    """POST /v1/recovery/decide accepts normalized tx_context directly."""
    tx_context = {
        "transaction_id": "tx_direct_123",
        "amount": 1500.0,
        "source_method": "card",
        "failure_code": "insufficient_funds",
        "bank": "HDFC",
        "network": "VISA",
        "merchant_tier": "TIER_1",
        "attempt_number": 1,
        "simulated_day": 15,
    }
    response = client.post("/v1/recovery/decide", json=tx_context)
    assert response.status_code == 200
    data = response.json()
    assert "should_retry" in data
    assert "expected_net_value_inr" in data


def test_no_internal_stack_trace_leaked_on_error():
    """Trigger a 500 error and verify response body contains no Python stack trace leak."""
    malformed_context = {"transaction_id": "tx_bad"}  # missing required source_method
    response = client.post("/v1/recovery/decide", json=malformed_context)
    assert response.status_code == 500
    body_str = response.text
    assert "Traceback" not in body_str
    assert 'File "' not in body_str
