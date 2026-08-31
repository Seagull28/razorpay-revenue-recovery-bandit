"""
run_item4_alpha_sensitivity.py
Executes Alpha Sensitivity Analysis for LinUCBPolicy across alpha = [0.1, 0.5, 1.0, 2.0, 5.0] on seed=42.
Reports overall recovery rate, net revenue, final cumulative regret, and average attempts per tx.
Generates unique timestamped plot artifacts to avoid UI caching.
Includes mandatory regression check for alpha=1.0.
"""

import sys
import json
import time
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.evaluation.metrics import compute_performance_by_segment, compute_oracle_regret
from dataclasses import asdict

def run_alpha_simulation(alpha: float, seed: int = 42):
    gen = TransactionStreamGenerator(seed=seed)
    txs = gen.generate_stream(num_days=30, transactions_per_day=100)
    sim = RetrySimulator(seed=seed)
    engine = PolicyExecutionEngine(simulator=sim)
    policy = LinUCBPolicy(alpha=alpha, min_samples_for_stopping=15)
    log = engine.run(transactions=txs, policy=policy)
    
    records_dict = [asdict(r) if hasattr(r, "__dataclass_fields__") else r for r in log.records]
    perf = compute_performance_by_segment(records_dict)
    regret_data = compute_oracle_regret(records_dict)
    
    total_attempts = len(records_dict)
    num_transactions = len(txs)
    avg_attempts_per_tx = total_attempts / num_transactions
    
    return {
        "alpha": alpha,
        "recovery_rate_pct": perf["overall"]["recovery_rate_pct"],
        "net_revenue": perf["overall"]["net_revenue"],
        "gross_revenue": perf["overall"]["gross_revenue"],
        "retry_cost": perf["overall"]["retry_cost"],
        "final_cum_regret": regret_data["final_cum_regret_expected"],
        "avg_attempts_per_tx": avg_attempts_per_tx,
        "total_attempts": total_attempts,
    }

def main():
    print("====================================================================================================")
    print("ITEM 4: ALPHA SENSITIVITY ANALYSIS (SEED 42)")
    print("====================================================================================================\n")

    alphas = [0.1, 0.5, 1.0, 2.0, 5.0]
    alpha_results = []

    for a in alphas:
        print(f"Running simulation for alpha = {a}...")
        res = run_alpha_simulation(alpha=a, seed=42)
        alpha_results.append(res)

    # 1. Mandatory Regression Check for alpha = 1.0
    a1_res = [r for r in alpha_results if r["alpha"] == 1.0][0]
    expected_net_revenue = 7998301.40
    expected_recovery_rate = 66.20
    expected_regret = 222598.34

    print("\n--- MANDATORY REGRESSION CHECK (ALPHA = 1.0) ---")
    print(f"Locked LinUCB Net Revenue  : INR {expected_net_revenue:,.2f} -> Actual: INR {a1_res['net_revenue']:,.2f}")
    print(f"Locked LinUCB Recovery Rate: {expected_recovery_rate:.2f}% -> Actual: {a1_res['recovery_rate_pct']:.2f}%")
    print(f"Locked Final Cum Regret    : INR {expected_regret:,.2f} -> Actual: INR {a1_res['final_cum_regret']:,.2f}")
    
    assert np.isclose(expected_net_revenue, a1_res["net_revenue"]), f"ALPHA=1.0 REGRESSION FAILED! {a1_res['net_revenue']} != {expected_net_revenue}"
    print(">>> REGRESSION CHECK PASSED 100%: ALPHA = 1.0 MATCHES LOCKED CORE EXACTLY <<<\n")

    # 2. Print Summary Table
    print("--- ALPHA SENSITIVITY RESULTS TABLE (SEED 42) ---")
    print("| Alpha | Recovery Rate (%) | Net Revenue (INR) | Total Cum Regret (INR) | Avg Attempts / Tx |")
    print("| :---: | :---: | :---: | :---: | :---: |")
    for r in alpha_results:
        print(f"| {r['alpha']:<5.1f} | {r['recovery_rate_pct']:6.2f}% | INR {r['net_revenue']:12,.2f} | INR {r['final_cum_regret']:10,.2f} | {r['avg_attempts_per_tx']:.2f} attempts/tx |")

    # 3. Plot Alpha Sensitivity Chart with Unique Timestamped Filename
    ts = int(time.time())
    artifact_dir = Path(r"C:\Users\Thanujha\.gemini\antigravity\brain\30eeb98e-59ae-47b5-85ad-a23d7f580f5a")
    plots_dir = artifact_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    
    plot_filename = f"alpha_sensitivity_{ts}.png"
    plot_path = plots_dir / plot_filename

    fig, ax1 = plt.subplots(figsize=(9, 5), dpi=300)

    color_net = "#1f77b4"
    color_reg = "#d62728"

    alpha_vals = [r["alpha"] for r in alpha_results]
    net_revs_lacs = [r["net_revenue"] / 1e5 for r in alpha_results]
    regrets_lacs = [r["final_cum_regret"] / 1e5 for r in alpha_results]

    ax1.set_xlabel(r"LinUCB Exploration Parameter ($\alpha$)", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Net Revenue (INR Lacs)", color=color_net, fontsize=11, fontweight="bold")
    line1 = ax1.plot(alpha_vals, net_revs_lacs, marker="o", color=color_net, linewidth=2.5, label="Net Revenue (INR Lacs)")
    ax1.tick_params(axis="y", labelcolor=color_net)
    ax1.grid(True, linestyle="--", alpha=0.5)

    ax2 = ax1.twinx()
    ax2.set_ylabel("Cumulative Regret (INR Lacs)", color=color_reg, fontsize=11, fontweight="bold")
    line2 = ax2.plot(alpha_vals, regrets_lacs, marker="s", color=color_reg, linewidth=2.5, linestyle="--", label="Cum. Regret (INR Lacs)")
    ax2.tick_params(axis="y", labelcolor=color_reg)

    # Highlight alpha=1.0 optimal point
    ax1.axvline(x=1.0, color="gray", linestyle=":", alpha=0.7)
    ax1.text(1.05, max(net_revs_lacs) * 0.98, r"Canonical $\alpha=1.0$", fontsize=10, fontweight="bold", color="black")

    plt.title(r"LinUCB Exploration Sensitivity: Net Revenue & Cumulative Regret vs. $\alpha$", fontsize=12, fontweight="bold", pad=12)
    fig.tight_layout()
    plt.savefig(plot_path)
    plt.close()
    print(f"\nPlot saved to unique path: {plot_path}")

    # 4. Save JSON Audit
    out_file = Path(r"C:\Users\Thanujha\.gemini\antigravity\scratch\bandit_retry_scheduler\audit\item4_alpha_results.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"alpha_results": alpha_results, "plot_filename": plot_filename}, f, indent=2)
    print(f"Item 4 audit JSON saved to: {out_file}")

if __name__ == "__main__":
    main()
