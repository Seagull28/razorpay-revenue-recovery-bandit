import sys
from pathlib import Path
import numpy as np

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.evaluation.harness import EvaluationHarness
from bandit_retry_scheduler.simulator.config import BASE_RECOVERY_PROBABILITIES, FailureCode, Bank

def run_seed_checkpoints(seed: int):
    harness = EvaluationHarness(seeds=[seed], num_days=30, transactions_per_day=100)
    seed_res = harness.run_seed_benchmark(seed)
    regret_data = seed_res["regret_data"]
    cum_expected = regret_data["cum_regret_expected"]
    records = seed_res["linucb_records"]
    
    tx_to_decision = {}
    seen = set()
    for idx, r in enumerate(records):
        tx_id = r["transaction_id"]
        if tx_id not in seen:
            seen.add(tx_id)
            tx_to_decision[len(seen)] = idx

    checkpoints = [100, 500, 1000, 1500, 2000, 2500, 3000]
    table_rows = []
    prev_cum = 0.0
    prev_t = 0
    
    for t in checkpoints:
        dec_idx = tx_to_decision.get(t, len(cum_expected) - 1)
        cum_val = float(cum_expected[dec_idx])
        inc_val = cum_val - prev_cum
        interval_len = t - prev_t
        inc_per_tx = inc_val / interval_len if interval_len > 0 else 0.0
        
        table_rows.append({
            "tx_checkpoint": t,
            "decision_idx": dec_idx + 1,
            "cum_regret": cum_val,
            "inc_regret": inc_val,
            "interval": f"{prev_t} -> {t}",
            "inc_per_tx": inc_per_tx,
        })
        prev_cum = cum_val
        prev_t = t

    print(f"\n================================================================================")
    print(f"REGRET CHECKPOINT TABLE (SEED {seed})")
    print(f"================================================================================")
    print(f"| Tx Checkpoint | Decision Step | Cum Regret (INR) | Interval | Incremental Regret (INR) | Inc Regret / Tx (INR) |")
    print(f"| :---: | :---: | :---: | :---: | :---: | :---: |")
    for r in table_rows:
        print(f"| T={r['tx_checkpoint']} | {r['decision_idx']} | INR {r['cum_regret']:,.2f} | {r['interval']} | INR {r['inc_regret']:,.2f} | **INR {r['inc_per_tx']:.2f}/tx** |")
    
    return seed_res

def check_ground_truth_pairs():
    print("\n================================================================================")
    print("GROUND TRUTH CONVERGENCE PAIR VERIFICATION")
    print("================================================================================")
    
    # Pair 1: issuer_timeout, Bank C
    p1_curves = BASE_RECOVERY_PROBABILITIES[FailureCode.ISSUER_TIMEOUT.value][Bank.BANK_C.value]
    p1_best = max(p1_curves, key=p1_curves.get)
    print(f"Pair 1 (issuer_timeout, Bank C):")
    print(f"  Base Curves: {p1_curves}")
    print(f"  Ground-Truth Optimal Arm: '{p1_best}' ({p1_curves[p1_best]*100:.1f}%)")
    
    # Pair 3: do_not_honor, Bank A
    p3_curves = BASE_RECOVERY_PROBABILITIES[FailureCode.DO_NOT_HONOR.value][Bank.BANK_A.value]
    p3_best = max(p3_curves, key=p3_curves.get)
    print(f"\nPair 3 (do_not_honor, Bank A):")
    print(f"  Base Curves: {p3_curves}")
    print(f"  Ground-Truth Optimal Arm: '{p3_best}' ({p3_curves[p3_best]*100:.1f}%)")

if __name__ == "__main__":
    check_ground_truth_pairs()
    run_seed_checkpoints(101)
    run_seed_checkpoints(2026)
