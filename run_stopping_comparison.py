"""
run_stopping_comparison.py
Executes a 3-way comparative benchmark across:
1. Fixed-Schedule Baseline (1d -> 3d -> 7d)
2. LinUCB with Old Tau-Decay Stopping Rule
3. LinUCB with New Currency-Denominated Expected-Value Stopping Rule (Phase 3.5)

Run on identical simulated traffic (seed=42, 30 days, 3,000 transactions).
"""

import json
from collections import defaultdict
from pathlib import Path
import sys

# Ensure root directory is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.policies.fixed_schedule import FixedSchedulePolicy
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator


def analyze_policy_audit(records):
    by_code = defaultdict(lambda: {
        "gross_revenue": 0.0,
        "retry_cost": 0.0,
        "attempts": 0,
        "tx_ids": set(),
        "recovered_ids": set(),
    })
    for r in records:
        code = r["context_vector"]["failure_code"]
        tx_id = r["transaction_id"]
        by_code[code]["tx_ids"].add(tx_id)
        by_code[code]["attempts"] += 1
        by_code[code]["retry_cost"] += 10.0
        if r["actual_outcome"] == 1:
            by_code[code]["recovered_ids"].add(tx_id)
            by_code[code]["gross_revenue"] += r["amount_recovered"]

    res = {}
    for code, d in by_code.items():
        res[code] = {
            "total_tx": len(d["tx_ids"]),
            "recovered_tx": len(d["recovered_ids"]),
            "rec_rate_pct": len(d["recovered_ids"]) / len(d["tx_ids"]) * 100.0 if d["tx_ids"] else 0.0,
            "gross_revenue": d["gross_revenue"],
            "retry_cost": d["retry_cost"],
            "net_revenue": d["gross_revenue"] - d["retry_cost"],
            "attempts": d["attempts"],
        }
    return res


def run_comparison():
    seed = 42
    num_days = 30
    tx_per_day = 100
    retry_cost = 10.0

    print("=" * 130)
    print("PHASE 3.5: 3-WAY STOPPING RULE BENCHMARK COMPARISON (3,000 Transactions / seed=42)")
    print("=" * 130)

    # Generate identical stream
    generator = TransactionStreamGenerator(seed=seed)
    transactions = generator.generate_stream(num_days=num_days, transactions_per_day=tx_per_day)

    # 1. Baseline
    sim_base = RetrySimulator(seed=seed)
    pol_base = FixedSchedulePolicy(max_attempts=4)
    eng_base = PolicyExecutionEngine(simulator=sim_base, retry_cost=retry_cost)
    log_base = AuditLogger()
    eng_base.run(transactions=transactions, policy=pol_base, logger=log_base)
    base_res = analyze_policy_audit(log_base.to_records())
    base_metrics = log_base.compute_summary_metrics()

    # 2. LinUCB Old Tau-Decay
    sim_old = RetrySimulator(seed=seed)
    pol_old = LinUCBPolicy(alpha=1.0, stopping_mode="tau_decay", soft_decay_base_threshold=0.0, max_attempts=4)
    eng_old = PolicyExecutionEngine(simulator=sim_old, retry_cost=retry_cost)
    log_old = AuditLogger()
    eng_old.run(transactions=transactions, policy=pol_old, logger=log_old)
    old_res = analyze_policy_audit(log_old.to_records())
    old_metrics = log_old.compute_summary_metrics()

    # 3. LinUCB New Expected-Value Rule (Phase 3.5)
    sim_new = RetrySimulator(seed=seed)
    pol_new = LinUCBPolicy(alpha=1.0, stopping_mode="expected_value", min_samples_for_stopping=15, max_attempts=4)
    eng_new = PolicyExecutionEngine(simulator=sim_new, retry_cost=retry_cost)
    log_new = AuditLogger()
    eng_new.run(transactions=transactions, policy=pol_new, logger=log_new)
    new_res = analyze_policy_audit(log_new.to_records())
    new_metrics = log_new.compute_summary_metrics()

    # Print 3-Way Per-Failure-Code Breakdown
    header = f"{'Failure Code':<20} | {'Policy':<18} | {'Total Tx':<8} | {'Attempts':<8} | {'Rec Tx':<6} | {'Rec Rate':<8} | {'Gross Rev (INR)':<16} | {'Cost (INR)':<10} | {'Net Rev (INR)':<16}"
    print(header)
    print("-" * 130)

    for code in sorted(base_res.keys()):
        b = base_res[code]
        o = old_res[code]
        n = new_res[code]

        print(f"{code:<20} | {'1. Fixed Baseline':<18} | {b['total_tx']:>8} | {b['attempts']:>8} | {b['recovered_tx']:>6} | {b['rec_rate_pct']:>7.2f}% | INR {b['gross_revenue']:>12,.2f} | INR {b['retry_cost']:>6,.2f} | INR {b['net_revenue']:>12,.2f}")
        print(f"{'':<20} | {'2. Old Tau-Decay':<18} | {o['total_tx']:>8} | {o['attempts']:>8} | {o['recovered_tx']:>6} | {o['rec_rate_pct']:>7.2f}% | INR {o['gross_revenue']:>12,.2f} | INR {o['retry_cost']:>6,.2f} | INR {o['net_revenue']:>12,.2f}")
        print(f"{'':<20} | {'3. New EV Rule (Fix)':<18} | {n['total_tx']:>8} | {n['attempts']:>8} | {n['recovered_tx']:>6} | {n['rec_rate_pct']:>7.2f}% | INR {n['gross_revenue']:>12,.2f} | INR {n['retry_cost']:>6,.2f} | INR {n['net_revenue']:>12,.2f}")

        delta_old = n['net_revenue'] - o['net_revenue']
        delta_base = n['net_revenue'] - b['net_revenue']
        print(f"{'  -> Fix vs Old / Base':<20} | {'Gain vs Old: ' + f'INR {delta_old:>+10,.2f}':<38} | {'Gain vs Base: ' + f'INR {delta_base:>+10,.2f}':<38}")
        print("-" * 130)

    # Overall Summary Table
    print("\n" + "=" * 130)
    print("PORTFOLIO OVERALL PERFORMANCE (3,000 Transactions)")
    print("=" * 130)
    print(f"{'Policy':<25} | {'Total Attempts':<15} | {'Recovered Tx':<12} | {'Recovery Rate':<15} | {'Gross Rev (INR)':<16} | {'Total Cost (INR)':<16} | {'Net Rev (INR)':<16}")
    print("-" * 130)
    print(f"{'1. Fixed Baseline':<25} | {base_metrics['total_attempts']:>15,} | {base_metrics['recovered_transactions']:>12,} | {base_metrics['recovery_rate_pct']:>14.2f}% | INR {base_metrics['total_revenue_recovered']:>12,.2f} | INR {base_metrics['total_retry_cost']:>12,.2f} | INR {base_metrics['net_revenue']:>12,.2f}")
    print(f"{'2. LinUCB (Old Tau-Decay)':<25} | {old_metrics['total_attempts']:>15,} | {old_metrics['recovered_transactions']:>12,} | {old_metrics['recovery_rate_pct']:>14.2f}% | INR {old_metrics['total_revenue_recovered']:>12,.2f} | INR {old_metrics['total_retry_cost']:>12,.2f} | INR {old_metrics['net_revenue']:>12,.2f}")
    print(f"{'3. LinUCB (New EV Rule)':<25} | {new_metrics['total_attempts']:>15,} | {new_metrics['recovered_transactions']:>12,} | {new_metrics['recovery_rate_pct']:>14.2f}% | INR {new_metrics['total_revenue_recovered']:>12,.2f} | INR {new_metrics['total_retry_cost']:>12,.2f} | INR {new_metrics['net_revenue']:>12,.2f}")
    print("-" * 130)

    total_gain_vs_old = new_metrics['net_revenue'] - old_metrics['net_revenue']
    total_gain_vs_base = new_metrics['net_revenue'] - base_metrics['net_revenue']
    print(f"-> Net Revenue Gain of EV Rule Fix vs. Old Tau-Decay: INR {total_gain_vs_old:>+12,.2f}")
    print(f"-> Net Revenue Gain of EV Rule Fix vs. Fixed Baseline: INR {total_gain_vs_base:>+12,.2f}")
    print("=" * 130)

    # Save new audit log to disk
    records = log_new.to_records()
    log_file = Path("bandit_audit_log.json")
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump({
            "policy": "LinUCB_EV_Rule",
            "stopping_mode": "expected_value",
            "min_samples_for_stopping": 5,
            "metrics": new_metrics,
            "records": records,
        }, f, indent=2)
    print(f"\nSaved updated LinUCB audit log to {log_file.resolve()}")

    return base_metrics, old_metrics, new_metrics


if __name__ == "__main__":
    run_comparison()
