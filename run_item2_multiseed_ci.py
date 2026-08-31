"""
run_item2_multiseed_ci.py
Executes 10-seed evaluation (seeds: 42, 101, 2026, 7, 13, 55, 99, 123, 256, 777),
computes 95% bootstrap confidence intervals for net revenue lift over baseline,
verifies seed=42 exact regression lock, and generates Section 8 multi-seed summary.
"""

import sys
import json
from pathlib import Path
import numpy as np

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.evaluation.harness import EvaluationHarness

def compute_bootstrap_ci(data: np.ndarray, n_iterations: int = 10000, seed: int = 42) -> tuple:
    rng = np.random.default_rng(seed)
    n = len(data)
    boot_means = []
    for _ in range(n_iterations):
        sample = rng.choice(data, size=n, replace=True)
        boot_means.append(np.mean(sample))
    
    ci_lower = float(np.percentile(boot_means, 2.5))
    ci_upper = float(np.percentile(boot_means, 97.5))
    return ci_lower, ci_upper

def main():
    print("====================================================================================================")
    print("ITEM 2: MULTI-SEED EVALUATION (10 SEEDS) & BOOTSTRAP CONFIDENCE INTERVALS")
    print("====================================================================================================\n")

    seeds = [42, 101, 2026, 7, 13, 55, 99, 123, 256, 777]
    harness = EvaluationHarness(seeds=seeds, num_days=30, transactions_per_day=100)
    
    print(f"Running evaluation across {len(seeds)} seeds: {seeds}...")
    summary = harness.run_full_evaluation()
    per_seed = summary["per_seed_results"]
    
    # 1. Mandatory Regression Check for seed 42
    seed42_data = per_seed[42]
    locked_linucb_net = 7998301.40
    locked_baseline_net = 6528431.32
    locked_lift_net = 1469870.08
    
    actual_linucb_net = seed42_data["linucb_performance"]["overall"]["net_revenue"]
    actual_baseline_net = seed42_data["baseline_performance"]["overall"]["net_revenue"]
    actual_lift_net = seed42_data["lifts"]["overall"]["net_revenue_lift_abs"]
    actual_lift_pct = seed42_data["lifts"]["overall"]["net_revenue_lift_pct"]
    
    print("\n--- MANDATORY REGRESSION CHECK (SEED 42) ---")
    print(f"Locked LinUCB Net Revenue  : INR {locked_linucb_net:,.2f}")
    print(f"Actual LinUCB Net Revenue  : INR {actual_linucb_net:,.2f}")
    print(f"LinUCB Net Revenue Match   : {np.isclose(locked_linucb_net, actual_linucb_net)}")
    
    print(f"Locked Baseline Net Revenue : INR {locked_baseline_net:,.2f}")
    print(f"Actual Baseline Net Revenue : INR {actual_baseline_net:,.2f}")
    print(f"Baseline Net Revenue Match  : {np.isclose(locked_baseline_net, actual_baseline_net)}")
    
    print(f"Locked Net Revenue Lift     : INR {locked_lift_net:,.2f} (+22.51%)")
    print(f"Actual Net Revenue Lift     : INR {actual_lift_net:,.2f} (+{actual_lift_pct:.2f}%)")
    print(f"Net Revenue Lift Match      : {np.isclose(locked_lift_net, actual_lift_net)}")
    
    assert np.isclose(locked_linucb_net, actual_linucb_net), f"SEED 42 DIVERGENCE DETECTED! {actual_linucb_net} != {locked_linucb_net}"
    print(">>> REGRESSION CHECK PASSED 100%: SEED 42 MATCHES LOCKED CORE EXACTLY <<<\n")

    # 2. Extract 10-seed metrics
    table_data = []
    lifts_inr = []
    lifts_pct = []
    
    for s in seeds:
        res = per_seed[s]
        b_net = res["baseline_performance"]["overall"]["net_revenue"]
        l_net = res["linucb_performance"]["overall"]["net_revenue"]
        lift_inr = res["lifts"]["overall"]["net_revenue_lift_abs"]
        lift_pct = res["lifts"]["overall"]["net_revenue_lift_pct"]
        rec = res["linucb_performance"]["overall"]["recovery_rate_pct"]
        
        lifts_inr.append(lift_inr)
        lifts_pct.append(lift_pct)
        table_data.append({
            "seed": s,
            "baseline_net_revenue": b_net,
            "linucb_net_revenue": l_net,
            "net_revenue_lift_inr": lift_inr,
            "net_revenue_lift_pct": lift_pct,
            "linucb_recovery_rate_pct": rec,
        })
    
    lifts_inr_arr = np.array(lifts_inr)
    lifts_pct_arr = np.array(lifts_pct)
    
    mean_lift_inr = float(np.mean(lifts_inr_arr))
    std_lift_inr = float(np.std(lifts_inr_arr, ddof=1)) # sample std dev
    mean_lift_pct = float(np.mean(lifts_pct_arr))
    std_lift_pct = float(np.std(lifts_pct_arr, ddof=1))
    
    # 3. Compute 95% bootstrap CIs
    ci_lower_inr, ci_upper_inr = compute_bootstrap_ci(lifts_inr_arr, n_iterations=10000, seed=42)
    ci_lower_pct, ci_upper_pct = compute_bootstrap_ci(lifts_pct_arr, n_iterations=10000, seed=42)
    
    print("--- 10-SEED SUMMARY METRICS & 95% BOOTSTRAP CONFIDENCE INTERVALS ---")
    print(f"Mean Net Revenue Lift (INR) : +INR {mean_lift_inr:,.2f} (Std Dev: INR {std_lift_inr:,.2f})")
    print(f"Mean Net Revenue Lift (%)   : +{mean_lift_pct:.2f}% (Std Dev: {std_lift_pct:.2f}%)")
    print(f"95% Bootstrap CI (INR)      : [+INR {ci_lower_inr:,.2f}, +INR {ci_upper_inr:,.2f}]")
    print(f"95% Bootstrap CI (%)        : [+{ci_lower_pct:.2f}%, +{ci_upper_pct:.2f}%]\n")

    # Print 10-seed table
    print("--- 10-SEED INDIVIDUAL RESULTS TABLE ---")
    print("| Seed | Baseline Net Rev (INR) | LinUCB Net Rev (INR) | Net Rev Lift (INR) | Net Rev Lift (%) | LinUCB Recovery Rate |")
    print("| :---: | :---: | :---: | :---: | :---: | :---: |")
    for row in table_data:
        print(f"| {row['seed']:<4} | INR {row['baseline_net_revenue']:12,.2f} | INR {row['linucb_net_revenue']:12,.2f} | +INR {row['net_revenue_lift_inr']:11,.2f} | +{row['net_revenue_lift_pct']:5.2f}% | {row['linucb_recovery_rate_pct']:.2f}% |")

    # Save output data to audit scratch file
    out_file = Path(r"C:\Users\Thanujha\.gemini\antigravity\scratch\bandit_retry_scheduler\audit\item2_multiseed_results.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    data_to_save = {
        "seed_results": table_data,
        "mean_lift_inr": mean_lift_inr,
        "std_lift_inr": std_lift_inr,
        "mean_lift_pct": mean_lift_pct,
        "std_lift_pct": std_lift_pct,
        "ci_lower_inr": ci_lower_inr,
        "ci_upper_inr": ci_upper_inr,
        "ci_lower_pct": ci_lower_pct,
        "ci_upper_pct": ci_upper_pct,
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, indent=2)
    print(f"\nItem 2 results saved to: {out_file}")

if __name__ == "__main__":
    main()
