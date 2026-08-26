"""
run_bandit.py
Executes the LinUCB Contextual Bandit policy against the 30-day synthetic transaction
simulator, records Section 7 audit logs with numeric expected values, reports cold-start
and overall metrics, and displays 3 exact-numeric verification traces.
"""

import json
from pathlib import Path
import sys
import numpy as np

# Ensure root directory is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.config import DELAY_ARMS
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator


def run_bandit_benchmark(
    seed: int = 42,
    num_days: int = 30,
    transactions_per_day: int = 100,
    retry_cost: float = 10.0,
    alpha: float = 1.0,
    output_log_path: str = "bandit_audit_log.json",
):
    print("=" * 85)
    print("PHASE 3: LinUCB CONTEXTUAL BANDIT POLICY SIMULATION")
    print("=" * 85)
    print(f"Simulation Configuration:")
    print(f" - Policy: LinUCB (Disjoint Ridge Regression, alpha={alpha})")
    print(f" - Seed: {seed}")
    print(f" - Duration: {num_days} simulated days")
    print(f" - Daily Failed Traffic: {transactions_per_day} transactions/day")
    print(f" - Total Transactions: {num_days * transactions_per_day}")
    print(f" - Feature Dimension: d = 19")
    print(f" - Retry Cost per Attempt: INR {retry_cost:.2f}")
    print("=" * 85)

    # 1. Generate identical 30-day transaction stream
    generator = TransactionStreamGenerator(seed=seed)
    transactions = generator.generate_stream(num_days=num_days, transactions_per_day=transactions_per_day)

    # 2. Instantiate Simulator & LinUCB Policy
    simulator = RetrySimulator(seed=seed)
    policy = LinUCBPolicy(alpha=alpha, max_attempts=4, retry_cost=retry_cost)
    engine = PolicyExecutionEngine(simulator=simulator, retry_cost=retry_cost)
    logger = AuditLogger()

    # Track decision details for selected trace scenarios
    # Scenario A: Early cold-start transaction (Transaction #5)
    # Scenario B: Mature transaction after high observation count (Transaction #850, Issuer Timeout Bank C)
    # Scenario C: Rare context transaction late in simulation (Transaction #2400, RuPay Do-Not-Honor)
    trace_checkpoints = {}
    target_tx_indices = {5: "Scenario A (Cold Start)", 850: "Scenario B (Learned Preference)", 2400: "Scenario C (Rare Context Late)"}

    # Step-by-step execution to capture decision traces before online update
    for idx, tx in enumerate(transactions, start=1):
        if idx in target_tx_indices:
            # Capture state before transaction is processed
            scores = policy.get_arm_scores(tx)
            decision = policy.select_arm(tx, attempt_number=1)
            trace_checkpoints[idx] = {
                "label": target_tx_indices[idx],
                "tx_index": idx,
                "context": dict(tx),
                "scores": scores,
                "arm_chosen": decision.arm_chosen,
                "ucb_expected_value": decision.expected_value,
            }

        engine.process_transaction(tx, policy, logger)

    # 3. Compute Summary Metrics
    metrics = logger.compute_summary_metrics()

    # Cold-start metrics (first 100 transactions)
    flat_records = logger.to_flat_records()
    early_tx_ids = set(tx["transaction_id"] for tx in transactions[:100])
    early_records = [r for r in flat_records if r["transaction_id"] in early_tx_ids]
    early_recovered = sum(1 for r in early_records if r["actual_outcome"] == 1)
    early_attempts = len(early_records)
    early_revenue = sum(r["amount_recovered"] for r in early_records)
    early_net_revenue = sum(r["reward"] for r in early_records)

    # 4. Display Overall Summary Metrics
    print("\n" + "=" * 85)
    print("LinUCB OVERALL SUMMARY METRICS (3,000 Transactions / 30 Days)")
    print("=" * 85)
    print(f"Total Transactions Processed   : {metrics['total_transactions']:,}")
    print(f"Total Retry Attempts Made      : {metrics['total_attempts']:,} ({metrics['total_attempts']/metrics['total_transactions']:.2f} avg attempts/tx)")
    print(f"Successfully Recovered Tx      : {metrics['recovered_transactions']:,}")
    print(f"Overall Recovery Rate          : {metrics['recovery_rate_pct']:.2f}% (vs Baseline: 52.17%)")
    print(f"Total Revenue Recovered        : INR {metrics['total_revenue_recovered']:,.2f}")
    print(f"Total Retry Cost Incurred      : INR {metrics['total_retry_cost']:,.2f}")
    print(f"Net Recovered Revenue          : INR {metrics['net_revenue']:,.2f} (vs Baseline: INR 6,528,431.32)")
    print(f"Avg Net Revenue / Failed Tx    : INR {metrics['avg_net_revenue_per_tx']:,.2f}")
    print("=" * 85)

    print("\n" + "=" * 85)
    print("COLD-START BEHAVIOR (First 100 Transactions)")
    print("=" * 85)
    print(f"Transactions Processed (Days 1): 100")
    print(f"Retry Attempts Executed        : {early_attempts}")
    print(f"Recovered Transactions         : {early_recovered} ({early_recovered/100*100:.1f}%)")
    print(f"Net Revenue Recovered          : INR {early_net_revenue:,.2f}")
    print(f"Cold-Start Arm Exploration     : Active explore/exploit balance driven by alpha={alpha} uncertainty bonus")
    print("=" * 85)

    print("\n" + "=" * 85)
    print("BREAKDOWN BY FAILURE CODE")
    print("=" * 85)
    print(f"{'Failure Code':<22} | {'Total Tx':<9} | {'Recovered':<10} | {'Rec Rate':<9} | {'Revenue (INR)':<15}")
    print("-" * 75)
    for code, stats in sorted(metrics["by_failure_code"].items()):
        print(f"{code:<22} | {stats['total_transactions']:<9} | {stats['recovered_transactions']:<10} | {stats['recovery_rate_pct']:>6.2f}% | INR {stats['total_recovered_inr']:>10,.2f}")
    print("-" * 75)

    print("\n" + "=" * 85)
    print("BREAKDOWN BY ISSUING BANK")
    print("=" * 85)
    print(f"{'Bank':<12} | {'Total Tx':<9} | {'Recovered':<10} | {'Rec Rate':<9} | {'Revenue (INR)':<15}")
    print("-" * 65)
    for bank, stats in sorted(metrics["by_bank"].items()):
        print(f"{bank:<12} | {stats['total_transactions']:<9} | {stats['recovered_transactions']:<10} | {stats['recovery_rate_pct']:>6.2f}% | INR {stats['total_recovered_inr']:>10,.2f}")
    print("-" * 65)

    # 5. Display the 3 Mandatory Exact-Numeric Traces
    print("\n" + "=" * 85)
    print("EXACT-NUMERIC VERIFICATION TRACES (Requirement #9: All 5 Arms Evaluated)")
    print("=" * 85)

    for idx, cp in trace_checkpoints.items():
        ctx = cp["context"]
        scores = cp["scores"]
        chosen = cp["arm_chosen"]

        # Find actual outcome for this transaction's attempt 1 from audit log
        matching = [r for r in flat_records if r["transaction_id"] == ctx["transaction_id"] and r["retry_attempt_number"] == 1]
        outcome_str = f"Outcome: {'SUCCESS' if matching and matching[0]['actual_outcome'] == 1 else 'FAILED'}, Reward: INR {matching[0]['reward']:,.2f}" if matching else ""

        print(f"\n[{cp['label']} — Transaction #{idx} ({ctx['transaction_id']})]")
        print(f"Context: failure_code='{ctx['failure_code']}', bank='{ctx['bank']}', network='{ctx['network']}', amount=INR {ctx['amount']:,.2f}, day={ctx['simulated_day']}")
        print(f"{'Arm':<6} | {'Exploitation (theta^T x)':<25} | {'Bonus (alpha*sqrt(var))':<25} | {'UCB Score':<15}")
        print("-" * 78)

        for arm in DELAY_ARMS:
            arm_data = scores[arm]
            is_chosen = " <-- [CHOSEN: argmax]" if arm == chosen else ""
            print(f"{arm:<6} | {arm_data['theta_dot_x']:>24.4f} | {arm_data['bonus']:>24.4f} | {arm_data['ucb_score']:>14.4f}{is_chosen}")

        print(f"Result: {outcome_str}")
        print("-" * 85)

    # 6. Save Audit Log to disk
    records = logger.to_records()
    log_file = Path(output_log_path)
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump({
            "policy": "LinUCB",
            "alpha": alpha,
            "metrics": metrics,
            "records": records,
        }, f, indent=2)
    print(f"\nSaved full LinUCB audit log ({len(records)} decision records) to {log_file.resolve()}")

    return metrics, logger


if __name__ == "__main__":
    run_bandit_benchmark()
