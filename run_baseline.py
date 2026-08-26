"""
run_baseline.py
Executes the fixed-schedule baseline policy (1d -> 3d -> 7d) against the 30-day
synthetic transaction simulator, records audit logs, and computes summary metrics.
"""

import json
from pathlib import Path
import sys

# Ensure root directory is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.policies.fixed_schedule import FixedSchedulePolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator


def run_baseline_benchmark(
    seed: int = 42,
    num_days: int = 30,
    transactions_per_day: int = 100,
    retry_cost: float = 10.0,
    output_log_path: str = "baseline_audit_log.json",
):
    print("=" * 80)
    print("PHASE 2: FIXED-SCHEDULE BASELINE POLICY SIMULATION (1d -> 3d -> 7d)")
    print("=" * 80)
    print(f"Simulation Configuration:")
    print(f" - Seed: {seed}")
    print(f" - Duration: {num_days} simulated days")
    print(f" - Daily Failed Traffic: {transactions_per_day} transactions/day")
    print(f" - Total Transactions: {num_days * transactions_per_day}")
    print(f" - Retry Cost per Attempt: INR {retry_cost:.2f}")
    print("=" * 80)

    # 1. Generate standard 30-day transaction stream (identical for Phase 3 LinUCB)
    generator = TransactionStreamGenerator(seed=seed)
    transactions = generator.generate_stream(num_days=num_days, transactions_per_day=transactions_per_day)

    # 2. Instantiate Simulator & Policy
    simulator = RetrySimulator(seed=seed)
    policy = FixedSchedulePolicy(max_attempts=4)
    engine = PolicyExecutionEngine(simulator=simulator, retry_cost=retry_cost)
    logger = AuditLogger()

    # 3. Execute Baseline Run
    engine.run(transactions=transactions, policy=policy, logger=logger)

    # 4. Compute Summary Metrics
    metrics = logger.compute_summary_metrics()

    # 5. Display Formatted Metrics
    print("\n" + "=" * 80)
    print("BASELINE OVERALL SUMMARY METRICS")
    print("=" * 80)
    print(f"Total Transactions Processed   : {metrics['total_transactions']:,}")
    print(f"Total Retry Attempts Made      : {metrics['total_attempts']:,} ({metrics['total_attempts']/metrics['total_transactions']:.2f} avg attempts/tx)")
    print(f"Successfully Recovered Tx      : {metrics['recovered_transactions']:,}")
    print(f"Overall Recovery Rate          : {metrics['recovery_rate_pct']:.2f}%")
    print(f"Total Revenue Recovered        : INR {metrics['total_revenue_recovered']:,.2f}")
    print(f"Total Retry Cost Incurred      : INR {metrics['total_retry_cost']:,.2f}")
    print(f"Net Recovered Revenue          : INR {metrics['net_revenue']:,.2f}")
    print(f"Avg Net Revenue / Failed Tx    : INR {metrics['avg_net_revenue_per_tx']:,.2f}")
    print("=" * 80)

    print("\n" + "=" * 80)
    print("BREAKDOWN BY FAILURE CODE")
    print("=" * 80)
    print(f"{'Failure Code':<22} | {'Total Tx':<9} | {'Recovered':<10} | {'Rec Rate':<9} | {'Revenue (INR)':<15}")
    print("-" * 75)
    for code, stats in sorted(metrics["by_failure_code"].items()):
        print(f"{code:<22} | {stats['total_transactions']:<9} | {stats['recovered_transactions']:<10} | {stats['recovery_rate_pct']:>6.2f}% | INR {stats['total_recovered_inr']:>10,.2f}")
    print("-" * 75)

    print("\n" + "=" * 80)
    print("BREAKDOWN BY ISSUING BANK")
    print("=" * 80)
    print(f"{'Bank':<12} | {'Total Tx':<9} | {'Recovered':<10} | {'Rec Rate':<9} | {'Revenue (INR)':<15}")
    print("-" * 65)
    for bank, stats in sorted(metrics["by_bank"].items()):
        print(f"{bank:<12} | {stats['total_transactions']:<9} | {stats['recovered_transactions']:<10} | {stats['recovery_rate_pct']:>6.2f}% | INR {stats['total_recovered_inr']:>10,.2f}")
    print("-" * 65)

    # 6. Sample Audit Log Entries (Section 7 Schema)
    records = logger.to_records()
    print("\n" + "=" * 80)
    print("SAMPLE AUDIT LOG RECORDS (Section 7 Schema: first 3 decisions)")
    print("=" * 80)
    for i, r in enumerate(records[:3], start=1):
        print(f"\n[Record #{i}]")
        print(f"  transaction_id   : {r['transaction_id']}")
        print(f"  timestamp        : {r['timestamp']}")
        print(f"  arm_chosen       : {r['arm_chosen']}")
        print(f"  expected_value   : {r['expected_value']}")
        print(f"  actual_outcome   : {r['actual_outcome']} ({'SUCCESS' if r['actual_outcome'] == 1 else 'FAILED'})")
        print(f"  amount_recovered : INR {r['amount_recovered']:,.2f}")
        print(f"  reward           : INR {r['reward']:,.2f}")
        print(f"  context_vector   : {json.dumps(r['context_vector'], indent=4)}")
    print("=" * 80)

    # 7. Save Audit Log to disk
    log_file = Path(output_log_path)
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump({
            "metrics": metrics,
            "records": records,
        }, f, indent=2)
    print(f"\nSaved full audit log ({len(records)} decision records) to {log_file.resolve()}")

    return metrics, logger


if __name__ == "__main__":
    run_baseline_benchmark()
