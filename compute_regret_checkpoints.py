import sys
from pathlib import Path
import numpy as np

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.evaluation.harness import EvaluationHarness

def main():
    harness = EvaluationHarness(seeds=[42], num_days=30, transactions_per_day=100)
    seed_res = harness.run_seed_benchmark(42)
    regret_data = seed_res["regret_data"]
    cum_expected = regret_data["cum_regret_expected"]
    
    # We want checkpoints at decision sequence T or transaction count T?
    # Let's check length of cum_expected (it's per decision, ~6581 total decisions for 3000 tx)
    # Or per unique transaction T?
    # The prompt asks for T=100, 500, 1000, 1500, 2000, 2500, 3000.
    # Since there are 3000 transactions, let's map decisions up to transaction t, or per decision step T.
    # Let's check both or map to transaction index t!
    
    records = seed_res["linucb_records"]
    tx_to_decision = {}
    tx_order = []
    seen = set()
    for idx, r in enumerate(records):
        tx_id = r["transaction_id"]
        if tx_id not in seen:
            seen.add(tx_id)
            tx_order.append(tx_id)
        tx_to_decision[len(seen)] = idx  # 1-indexed transaction to 0-indexed decision

    checkpoints = [100, 500, 1000, 1500, 2000, 2500, 3000]
    
    print("=" * 80)
    print("REGRET CHECKPOINT ANALYSIS (SEED 42)")
    print("=" * 80)
    
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

    print(f"| Tx Checkpoint | Decision Step | Cum Regret (INR) | Interval | Incremental Regret (INR) | Inc Regret / Tx (INR) |")
    print(f"| :---: | :---: | :---: | :---: | :---: | :---: |")
    for r in table_rows:
        print(f"| T={r['tx_checkpoint']} | {r['decision_idx']} | INR {r['cum_regret']:,.2f} | {r['interval']} | INR {r['inc_regret']:,.2f} | **INR {r['inc_per_tx']:.2f}/tx** |")

if __name__ == "__main__":
    main()
