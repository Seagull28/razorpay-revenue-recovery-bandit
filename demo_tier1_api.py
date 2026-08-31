"""
demo_tier1_api.py
Demonstration script showing RecoverFlow Phase 5 Tier 1 API outputs,
eligibility gate checks, explainability strings, and audit logging.
"""

import sys
from pathlib import Path

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

import json
from bandit_retry_scheduler.api import get_retry_decision, AuditService
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.simulator.config import FailureCode, Bank, Network


def main():
    logger = AuditLogger()
    policy = LinUCBPolicy()
    audit_svc = AuditService(audit_logger=logger)

    print("====================================================================================================")
    print("RECOVERFLOW TIER 1 API DEMONSTRATION")
    print("====================================================================================================\n")

    # Sample 1: Eligible transaction (issuer_timeout)
    tx1 = {
        "transaction_id": "tx_timeout_001",
        "amount": 2500.0,
        "failure_code": FailureCode.ISSUER_TIMEOUT.value,
        "bank": Bank.BANK_C.value,
        "network": Network.VISA.value,
        "customer_prior_success_count": "1-3",
        "customer_prior_failures_this_cycle": "0",
        "day_of_month_bucket": "mid",
    }
    res1 = get_retry_decision(tx1, policy=policy, attempt_number=1, audit_logger=logger)

    print("--- SAMPLE 1: Eligible Retry (issuer_timeout on Bank C) ---")
    print(f"Transaction ID : {res1['transaction_id']}")
    print(f"Should Retry   : {res1['should_retry']}")
    print(f"Delay Bucket   : {res1['recommended_delay']}")
    print(f"Expected Value : INR {res1['expected_net_value_inr']:,.2f}")
    print(f"Explanation    : {res1['explanation']}\n")

    # Sample 2: Card Expired Attempt 1 (Eligible for Attempt 1)
    tx2 = {
        "transaction_id": "tx_card_exp_002",
        "amount": 1200.0,
        "failure_code": FailureCode.CARD_EXPIRED.value,
        "bank": Bank.BANK_A.value,
    }
    res2_att1 = get_retry_decision(tx2, policy=policy, attempt_number=1, audit_logger=logger)
    res2_att2 = get_retry_decision(tx2, policy=policy, attempt_number=2, audit_logger=logger)

    print("--- SAMPLE 2: Card Expired Eligibility Gate Check ---")
    print(f"Attempt 1 -> Should Retry: {res2_att1['should_retry']}, Reason: {res2_att1['stop_reason']}")
    print(f"Attempt 2 -> Should Retry: {res2_att2['should_retry']}, Stop Reason: {res2_att2['stop_reason']}")
    print(f"Explanation: {res2_att2['explanation']}\n")

    # Sample 3: High-ticket insufficient_funds
    tx3 = {
        "transaction_id": "tx_funds_003",
        "amount": 8500.0,
        "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
        "bank": Bank.BANK_B.value,
        "network": Network.MASTERCARD.value,
        "customer_prior_success_count": "4+",
        "customer_prior_failures_this_cycle": "0",
        "day_of_month_bucket": "late",
    }
    res3 = get_retry_decision(tx3, policy=policy, attempt_number=1, audit_logger=logger)

    print("--- SAMPLE 3: High-Ticket Balance Replenishment (insufficient_funds on Bank B) ---")
    print(f"Recommended Delay : {res3['recommended_delay']}")
    print(f"Expected Net Value: INR {res3['expected_net_value_inr']:,.2f}")
    print(f"Explanation       : {res3['explanation']}\n")

    # Audit Trail History Check
    history = audit_svc.get_transaction_history("tx_card_exp_002")
    print("--- AUDIT TRAIL QUERY ---")
    print(f"Audit Records for 'tx_card_exp_002': {len(history)} entries logged")
    print("====================================================================================================\n")


if __name__ == "__main__":
    main()
