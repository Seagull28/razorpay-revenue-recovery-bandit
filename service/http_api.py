"""Proof-of-concept HTTP service. No database, no authentication, no persistence — single in-process policy instance. Not production-hardened; demonstrates that the decision logic is cleanly separable from the dashboard and callable over HTTP."""

import sys
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

# Project-relative root setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from bandit_retry_scheduler.core.action_registry import ActionRegistry
from bandit_retry_scheduler.policies.v2_linucb import V2LinUCBPolicy
from bandit_retry_scheduler.core.v2_ev_estimator import V2EVEstimator
from bandit_retry_scheduler.simulator.v2_environment import V2RetrySimulator
from bandit_retry_scheduler.api.v2_decision_service import V2DecisionService
from bandit_retry_scheduler.runner.v2_engine import V2PolicyExecutionEngine
from service.razorpay_adapter import parse_razorpay_webhook, RazorpayAdapterError

app = FastAPI(
    title="RecoverFlow V2 Decision Engine API",
    description="Proof-of-concept HTTP service wrapping V2 recovery decision logic.",
    version="2.0.0",
)

# In-memory singletons initialized once at import time
registry = ActionRegistry()
policy = V2LinUCBPolicy(registry=registry)
ev_estimator = V2EVEstimator(registry=registry)
simulator = V2RetrySimulator()
engine = V2PolicyExecutionEngine(simulator=simulator, registry=registry, policy=policy)
decision_service = engine.decision_service
decision_service.ev_estimator = ev_estimator


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/v1/webhooks/razorpay")
async def handle_razorpay_webhook(request: Request, attempt_number: int = Query(1, ge=1)):
    """
    Parses a Razorpay payment.failed webhook payload and returns a V2 recovery decision.
    """
    try:
        try:
            raw_payload = await request.json()
        except Exception as e:
            raise RazorpayAdapterError(f"Invalid JSON body: {e}")

        tx_context = parse_razorpay_webhook(raw_payload)
        tx_context["attempt_number"] = attempt_number

        decision = decision_service.get_v2_retry_decision(
            transaction=tx_context,
            attempt_number=attempt_number,
        )

        chosen_action = decision.get("action_chosen")
        action_dict = None
        if chosen_action is not None:
            action_dict = {
                "action_id": chosen_action.action_id,
                "action_type": chosen_action.action_type,
                "source_method": chosen_action.source_method,
                "target_method": chosen_action.target_method,
                "delay": chosen_action.delay,
            }

        return {
            "should_retry": decision.get("should_retry", False),
            "action_chosen": action_dict,
            "expected_net_value_inr": decision.get("expected_net_value_inr", 0.0),
            "stop_reason": decision.get("stop_reason"),
        }
    except RazorpayAdapterError as e:
        return JSONResponse(status_code=422, content={"detail": str(e)})
    except Exception:
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.post("/v1/recovery/decide")
async def decide_recovery_direct(request: Request, attempt_number: Optional[int] = Query(None)):
    """
    Direct endpoint accepting a pre-normalized tx_context dictionary.
    """
    try:
        try:
            tx_context = await request.json()
        except Exception:
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})

        if not isinstance(tx_context, dict):
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})

        if attempt_number is not None:
            tx_context["attempt_number"] = attempt_number

        attempt_num = tx_context.get("attempt_number", 1)

        decision = decision_service.get_v2_retry_decision(
            transaction=tx_context,
            attempt_number=attempt_num,
        )

        chosen_action = decision.get("action_chosen")
        action_dict = None
        if chosen_action is not None:
            action_dict = {
                "action_id": chosen_action.action_id,
                "action_type": chosen_action.action_type,
                "source_method": chosen_action.source_method,
                "target_method": chosen_action.target_method,
                "delay": chosen_action.delay,
            }

        return {
            "should_retry": decision.get("should_retry", False),
            "action_chosen": action_dict,
            "expected_net_value_inr": decision.get("expected_net_value_inr", 0.0),
            "stop_reason": decision.get("stop_reason"),
        }
    except Exception:
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
