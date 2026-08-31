"""
verify_pretrained_arm_scores.py
Verifies and prints the 5-arm score breakdowns for sample transactions post-pretraining (1,000 transactions).
Demonstrates real, differentiated theta_dot_x, bonus, and UCB values across arms.
"""

import sys
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.config import FailureCode, Bank, Network
from bandit_retry_scheduler.api.decision_service import get_retry_decision
from bandit_retry_scheduler.api.explainability import generate_decision_explanation

def main():
    print("====================================================================================================")
    print("PRE-TRAINING POLICY ON 1,000 SIMULATED TRANSACTIONS (SEED 42)...")
    print("====================================================================================================\n")

    policy = LinUCBPolicy(min_samples_for_stopping=15)
    simulator = RetrySimulator(seed=42)
    stream_gen = TransactionStreamGenerator(seed=42)
    engine = PolicyExecutionEngine(simulator=simulator)
    stream = stream_gen.generate_stream(num_days=10, transactions_per_day=100)
    engine.run(stream, policy=policy, logger=None)

    preset_txs = {
        "1. Insufficient Funds (High-Ticket, Bank B)": {
            "transaction_id": "tx_demo_insufficient_funds_001",
            "amount": 5000.0,
            "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
            "bank": Bank.BANK_B.value,
            "network": Network.VISA.value,
            "customer_prior_success_count": "4+",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "salary_cycle",
            "attempt_number": 1,
        },
        "2. Issuer Timeout (Standard, Bank C)": {
            "transaction_id": "tx_demo_issuer_timeout_002",
            "amount": 1500.0,
            "failure_code": FailureCode.ISSUER_TIMEOUT.value,
            "bank": Bank.BANK_C.value,
            "network": Network.MASTERCARD.value,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "early",
            "attempt_number": 1,
        },
        "3. Do Not Honor (High-Ticket, Bank A)": {
            "transaction_id": "tx_demo_do_not_honor_003",
            "amount": 4500.0,
            "failure_code": FailureCode.DO_NOT_HONOR.value,
            "bank": Bank.BANK_A.value,
            "network": Network.RUPAY.value,
            "customer_prior_success_count": "0",
            "customer_prior_failures_this_cycle": "1",
            "day_of_month_bucket": "mid",
            "attempt_number": 1,
        },
        "4. Generic Decline (Standard, Bank A)": {
            "transaction_id": "tx_demo_generic_decline_005",
            "amount": 1200.0,
            "failure_code": FailureCode.GENERIC_DECLINE.value,
            "bank": Bank.BANK_A.value,
            "network": Network.MASTERCARD.value,
            "customer_prior_success_count": "4+",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "late",
            "attempt_number": 1,
        },
    }

    for label, tx in preset_txs.items():
        decision = get_retry_decision(transaction=tx, policy=policy, attempt_number=1)
        rec_delay = decision["recommended_delay"]
        
        print(f"====================================================================================================")
        print(f"SAMPLE TRANSACTION: {label}")
        print(f"Recommended Arm : {rec_delay} (Should Retry: {decision['should_retry']})")
        print(f"Explanation     : {decision['explanation']}")
        print(f"----------------------------------------------------------------------------------------------------")
        
        rows = []
        for arm in ["1hr", "6hr", "1d", "3d", "7d"]:
            s = decision["arm_scores"][arm]
            is_rec = (arm == rec_delay and decision["should_retry"])
            rows.append({
                "Arm": f"⭐ {arm}" if is_rec else f"  {arm}",
                "Point Estimate θ^T x (INR)": f"INR {s['theta_dot_x']:>9,.2f}",
                "Bonus (INR)": f"INR {s['bonus']:>5,.2f}",
                "Combined UCB Score (INR)": f"INR {s['ucb_score']:>9,.2f}",
                "Pulls": s["pull_count"],
            })
        
        df = pd.DataFrame(rows)
        print(df.to_string(index=False))
        print("\n")

if __name__ == "__main__":
    main()
