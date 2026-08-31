import sys
from pathlib import Path
from collections import Counter

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.evaluation.harness import EvaluationHarness

def main():
    harness = EvaluationHarness(seeds=[42], num_days=30, transactions_per_day=100)
    seed_res = harness.run_seed_benchmark(42)
    records = seed_res["linucb_records"]
    
    target_records = [
        r for r in records
        if r["context_vector"]["failure_code"] == "insufficient_funds"
        and r["context_vector"]["bank"] == "Bank B"
    ]
    
    print(f"Total decisions for (insufficient_funds, Bank B): {len(target_records)}")
    
    # Group decisions by occurrence index and transaction_id
    tx_ids = []
    seen = set()
    for r in target_records:
        tx_id = r["transaction_id"]
        if tx_id not in seen:
            seen.add(tx_id)
            tx_ids.append(tx_id)
            
    print(f"Total unique transactions for (insufficient_funds, Bank B): {len(tx_ids)}")
    
    print("\nFirst 20 decisions:")
    for idx, r in enumerate(target_records[:20]):
        ctx = r["context_vector"]
        print(f"Dec #{idx+1}: tx={r['transaction_id']}, attempt={ctx['retry_attempt_number']}, arm={r['arm_chosen']}, outcome={r['actual_outcome']}, amt={r['amount_recovered']}")

    print("\nArm distribution in first 50 decisions:")
    c_first50 = Counter([r['arm_chosen'] for r in target_records[:50]])
    print(c_first50)
    
    print("\nArm distribution in last 50 decisions:")
    c_last50 = Counter([r['arm_chosen'] for r in target_records[-50:]])
    print(c_last50)
    
    print("\nOverall arm distribution for (insufficient_funds, Bank B):")
    c_all = Counter([r['arm_chosen'] for r in target_records])
    print(c_all)

if __name__ == "__main__":
    main()
