import sys
from pathlib import Path

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.api import get_retry_decision
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.config import FailureCode, Bank, Network

def main():
    print("====================================================================================================")
    print("LIVE PARTIALLY-TRAINED LINUCB POLICY EXPLAINABILITY OUTPUT")
    print("====================================================================================================\n")

    # 1. Instantiate policy and simulator, train policy on 500 transactions
    policy = LinUCBPolicy(min_samples_for_stopping=15)
    sim = RetrySimulator(seed=42)
    gen = TransactionStreamGenerator(seed=42)
    tx_stream = gen.generate_stream(num_days=5, transactions_per_day=100) # 500 transactions

    print(f"Training LinUCB policy on {len(tx_stream)} transactions...")
    for tx in tx_stream:
        # Simulate standard policy step
        stop, _ = policy.should_stop(tx, attempt_number=1)
        if not stop:
            decision = policy.select_arm(tx, attempt_number=1)
            arm = decision.arm_chosen
            success, amount_recovered = sim.simulate_retry(tx, arm)
            reward = amount_recovered - 10.0 if success else -10.0
            policy.update(tx, arm, reward)

    print("Training complete! Evaluating live decisions on partially-trained policy state:\n")

    # Live Case 1: issuer_timeout on Bank C
    tx1 = {
        "transaction_id": "tx_live_timeout_001",
        "amount": 2500.0,
        "failure_code": FailureCode.ISSUER_TIMEOUT.value,
        "bank": Bank.BANK_C.value,
        "network": Network.VISA.value,
        "customer_prior_success_count": "1-3",
        "customer_prior_failures_this_cycle": "0",
        "day_of_month_bucket": "mid",
    }
    res1 = get_retry_decision(tx1, policy=policy, attempt_number=1)

    print("--- LIVE TEST 1: issuer_timeout on Bank C ---")
    print(f"Transaction ID       : {res1['transaction_id']}")
    print(f"Should Retry         : {res1['should_retry']}")
    print(f"Recommended Delay    : {res1['recommended_delay']}")
    print(f"Expected Net Value   : INR {res1['expected_net_value_inr']:,.2f}")
    print(f"Raw Explanation      : {res1['explanation']}\n")

    # Live Case 2: insufficient_funds on Bank B
    tx2 = {
        "transaction_id": "tx_live_funds_002",
        "amount": 5000.0,
        "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
        "bank": Bank.BANK_B.value,
        "network": Network.MASTERCARD.value,
        "customer_prior_success_count": "4+",
        "customer_prior_failures_this_cycle": "0",
        "day_of_month_bucket": "late",
    }
    res2 = get_retry_decision(tx2, policy=policy, attempt_number=1)

    print("--- LIVE TEST 2: insufficient_funds on Bank B ---")
    print(f"Transaction ID       : {res2['transaction_id']}")
    print(f"Should Retry         : {res2['should_retry']}")
    print(f"Recommended Delay    : {res2['recommended_delay']}")
    print(f"Expected Net Value   : INR {res2['expected_net_value_inr']:,.2f}")
    print(f"Raw Explanation      : {res2['explanation']}\n")

    # Live Case 3: Card Expired Attempt 2
    tx3 = {
        "transaction_id": "tx_live_cardexp_003",
        "amount": 1500.0,
        "failure_code": FailureCode.CARD_EXPIRED.value,
        "bank": Bank.BANK_A.value,
    }
    res3 = get_retry_decision(tx3, policy=policy, attempt_number=2)

    print("--- LIVE TEST 3: card_expired Attempt 2 ---")
    print(f"Transaction ID       : {res3['transaction_id']}")
    print(f"Should Retry         : {res3['should_retry']}")
    print(f"Stop Reason          : {res3['stop_reason']}")
    print(f"Raw Explanation      : {res3['explanation']}\n")

    # Live Case 4: do_not_honor on Bank A (Mature EV Halt)
    tx4 = {
        "transaction_id": "tx_live_dnh_004",
        "amount": 1500.0,
        "failure_code": FailureCode.DO_NOT_HONOR.value,
        "bank": Bank.BANK_A.value,
        "network": Network.RUPAY.value,
        "customer_prior_success_count": "0",
        "customer_prior_failures_this_cycle": "2+",
        "day_of_month_bucket": "late",
    }
    res4 = get_retry_decision(tx4, policy=policy, attempt_number=2)

    print("--- LIVE TEST 4: do_not_honor on Bank A (Mature EV Halt) ---")
    print(f"Transaction ID       : {res4['transaction_id']}")
    print(f"Should Retry         : {res4['should_retry']}")
    print(f"Stop Reason          : {res4['stop_reason']}")
    print(f"Raw Explanation      : {res4['explanation']}\n")

    print("====================================================================================================")

if __name__ == "__main__":
    main()
