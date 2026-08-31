import sys
from pathlib import Path
from collections import Counter

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.evaluation.harness import EvaluationHarness
from bandit_retry_scheduler.simulator.config import BASE_RECOVERY_PROBABILITIES, FailureCode, Bank
from bandit_retry_scheduler.simulator.ground_truth import calculate_recovery_probability

def main():
    harness = EvaluationHarness(seeds=[42], num_days=30, transactions_per_day=100)
    seed_res = harness.run_seed_benchmark(42)
    records = seed_res["linucb_records"]
    
    target = [r for r in records if r["context_vector"]["failure_code"] == "do_not_honor" and r["context_vector"]["bank"] == "Bank A"]
    
    print(f"Total decisions for (do_not_honor, Bank A): {len(target)}")
    
    # Check ground truth EV for different amounts and modifiers
    print("\nGround Truth Probabilities:")
    curves = BASE_RECOVERY_PROBABILITIES[FailureCode.DO_NOT_HONOR.value][Bank.BANK_A.value]
    print(curves)
    
    print("\nExpected Net Revenue for INR 5,000 High-Ticket Median:")
    for arm, p in curves.items():
        ev = p * 5000.0 - 10.0
        print(f"  Arm {arm}: P={p*100:.1f}%, EV=INR {ev:.2f}")
        
    print("\nExpected Net Revenue for INR 1,500 Standard Amount:")
    for arm, p in curves.items():
        ev = p * 1500.0 - 10.0
        print(f"  Arm {arm}: P={p*100:.1f}%, EV=INR {ev:.2f}")

    # Inspect last 40 window decisions
    last_40 = target[-40:]
    c_last40 = Counter([r["arm_chosen"] for r in last_40])
    print("\nLast 40 decisions arm distribution:")
    for arm, count in c_last40.items():
        print(f"  {arm}: {count} / 40 ({count/40*100:.1f}%)")

if __name__ == "__main__":
    main()
