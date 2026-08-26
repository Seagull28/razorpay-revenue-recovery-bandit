"""
investigate_dnh.py
Empirical analysis of do_not_honor across multiple seeds and min_samples thresholds.
Tests min_samples_for_stopping in [5, 10, 15, 20, 25] across seeds [42, 100, 2026].
"""

import json
from collections import defaultdict
from pathlib import Path
import sys

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.policies.fixed_schedule import FixedSchedulePolicy
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator


def analyze_records(records):
    by_code = defaultdict(lambda: {"gross": 0.0, "cost": 0.0, "att": 0, "tx": set(), "rec": set()})
    for r in records:
        code = r["context_vector"]["failure_code"]
        tx_id = r["transaction_id"]
        by_code[code]["tx"].add(tx_id)
        by_code[code]["att"] += 1
        by_code[code]["cost"] += 10.0
        if r["actual_outcome"] == 1:
            by_code[code]["rec"].add(tx_id)
            by_code[code]["gross"] += r["amount_recovered"]
    
    res = {}
    for c, d in by_code.items():
        res[c] = {
            "tx": len(d["tx"]),
            "rec": len(d["rec"]),
            "net": d["gross"] - d["cost"],
            "att": d["att"],
            "rate": len(d["rec"]) / len(d["tx"]) * 100.0 if d["tx"] else 0.0
        }
    return res


def run_experiment():
    seeds = [42, 101, 2026]
    thresholds = [5, 10, 15, 20, 30]

    print("=" * 100)
    print("EMPIRICAL EXPERIMENT: do_not_honor & PORTFOLIO ACROSS THRESHOLDS AND SEEDS")
    print("=" * 100)

    for seed in seeds:
        print(f"\n--- SEED {seed} ---")
        gen = TransactionStreamGenerator(seed=seed)
        txs = gen.generate_stream(num_days=30, transactions_per_day=100)

        # Baseline
        sim_b = RetrySimulator(seed=seed)
        pol_b = FixedSchedulePolicy(max_attempts=4)
        eng_b = PolicyExecutionEngine(simulator=sim_b, retry_cost=10.0)
        log_b = AuditLogger()
        eng_b.run(txs, pol_b, log_b)
        base_res = analyze_records(log_b.to_records())
        base_tot = log_b.compute_summary_metrics()

        print(f"Fixed Baseline -> do_not_honor: Rec={base_res['do_not_honor']['rec']}/{base_res['do_not_honor']['tx']} ({base_res['do_not_honor']['rate']:.2f}%), Net=INR {base_res['do_not_honor']['net']:,.2f} | Total Net=INR {base_tot['net_revenue']:,.2f}")

        for thresh in thresholds:
            sim_l = RetrySimulator(seed=seed)
            pol_l = LinUCBPolicy(alpha=1.0, stopping_mode="expected_value", min_samples_for_stopping=thresh, max_attempts=4)
            eng_l = PolicyExecutionEngine(simulator=sim_l, retry_cost=10.0)
            log_l = AuditLogger()
            eng_l.run(txs, pol_l, log_l)
            lin_res = analyze_records(log_l.to_records())
            lin_tot = log_l.compute_summary_metrics()

            dnh = lin_res["do_not_honor"]
            diff_dnh = dnh["net"] - base_res["do_not_honor"]["net"]
            diff_tot = lin_tot["net_revenue"] - base_tot["net_revenue"]
            print(f"LinUCB (min_samples={thresh:>2}) -> DNH: Rec={dnh['rec']}/{dnh['tx']} ({dnh['rate']:>5.2f}%), Net=INR {dnh['net']:>10,.2f} (Diff: INR {diff_dnh:>+10,.2f}) | Total Net=INR {lin_tot['net_revenue']:>12,.2f} (Lift: INR {diff_tot:>+12,.2f})")


if __name__ == "__main__":
    run_experiment()
