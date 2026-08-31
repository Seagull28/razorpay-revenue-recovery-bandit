"""
demo_tier2_full_loop.py
Demonstration script executing a 50-transaction stream through the COMPLETE RecoverFlow Tier 1 & Tier 2 API Stack:
For each transaction, loops through retry attempts (attempt 1..4) until payment is recovered or should_retry is False:
1. check_eligibility()
2. get_retry_decision()
3. execute_retry_action()
4. process_outcome_and_update()

Confirms multi-attempt lifecycle fidelity, online learning, and audit trail generation.
"""

import sys
from pathlib import Path

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.api import (
    get_retry_decision,
    execute_retry_action,
    process_outcome_and_update,
    AuditService,
)
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator
from bandit_retry_scheduler.audit.logger import AuditLogger


def main():
    print("====================================================================================================")
    print("RECOVERFLOW TIER 2 FULL MULTI-ATTEMPT API STACK DEMONSTRATION (50 TRANSACTIONS)")
    print("====================================================================================================\n")

    policy = LinUCBPolicy(min_samples_for_stopping=15)
    sim = RetrySimulator(seed=42)
    logger = AuditLogger()
    audit_svc = AuditService(audit_logger=logger)
    gen = TransactionStreamGenerator(seed=42)

    # Generate 50 transactions
    transactions = gen.generate_stream(num_days=1, transactions_per_day=50)

    total_tx = len(transactions)
    total_recovered = 0
    total_gross_rev = 0.0
    total_cost = 0.0
    retries_executed = 0
    halted_decisions = 0

    print(f"Executing {total_tx} transactions through multi-attempt API stack loop:\n")

    for idx, tx in enumerate(transactions, start=1):
        tx_id = tx["transaction_id"]
        amount = tx["amount"]
        attempt = 1
        recovered = False
        attempt_history = []

        while attempt <= 4 and not recovered:
            # Step 1: Query API for Retry Decision (includes Eligibility Gate check)
            decision = get_retry_decision(
                tx,
                policy=policy,
                attempt_number=attempt,
                previous_success=recovered,
                audit_logger=logger,
            )

            # Step 2: Bounded Action Execution
            exec_res = execute_retry_action(tx, decision, sim)

            # Step 3: Online Feedback Loop Update
            process_outcome_and_update(tx, decision, exec_res, policy, audit_logger=logger)

            if not decision["should_retry"]:
                halted_decisions += 1
                attempt_history.append(f"Att {attempt}: HALTED ({decision['stop_reason']})")
                break

            retries_executed += 1
            total_cost += 10.0
            attempt_history.append(f"Att {attempt} [{exec_res['delay_executed']}]: {exec_res['outcome']}")

            if exec_res["outcome"] == "success":
                total_recovered += 1
                total_gross_rev += exec_res["amount_recovered"]
                recovered = True
                break

            attempt += 1

        if idx <= 10 or idx % 10 == 0:
            history_str = " | ".join(attempt_history)
            print(f"Tx {idx:02d} [{tx['failure_code']} on {tx['bank']}]: {history_str}")

    net_revenue = total_gross_rev - total_cost
    recovery_rate = (total_recovered / total_tx) * 100.0

    print("\n====================================================================================================")
    print("50-TRANSACTION MULTI-ATTEMPT API STACK EXECUTION SUMMARY")
    print("====================================================================================================")
    print(f"Total Transactions Processed : {total_tx}")
    print(f"Total Retry Attempts Executed: {retries_executed} ({retries_executed/total_tx:.2f} attempts/tx)")
    print(f"Halted Decisions / Stops     : {halted_decisions}")
    print(f"Successful Recoveries        : {total_recovered} ({recovery_rate:.1f}% recovery rate)")
    print(f"Gross Revenue Recovered      : INR {total_gross_rev:,.2f}")
    print(f"Total Retry Costs            : INR {total_cost:,.2f}")
    print(f"Net Revenue Realized         : INR {net_revenue:,.2f}")
    print(f"Total Audit Logged Records   : {len(logger.records)}")
    print("====================================================================================================\n")


if __name__ == "__main__":
    main()
