"""
retry_cost_sensitivity_analysis.py
Post-hoc sensitivity analysis script for RecoverFlow retry cost realism.

Reads existing canonical Phase 1 benchmark results (audit/evaluation_results/phase1/phase1_per_seed_results.json)
and recomputes net revenue metrics under an alternative, per-delay-arm cost table:
  {"1hr": 18.0, "6hr": 14.0, "1d": 10.0, "3d": 12.0, "7d": 15.0}

Does NOT modify any policies, simulator, or canonical evaluation artifacts.
Purely additive sensitivity check.
"""

import os
import sys
import json
from pathlib import Path
import numpy as np

# Root directory setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Illustrative alternative cost table (INR per attempt per arm)
# Faster retries (1hr/6hr) carry higher gateway/network congestion fees.
# Longer delays (3d/7d) carry opportunity cost and customer fatigue penalty.
# 1d delay serves as baseline (10.0 INR).
ALTERNATIVE_COST_TABLE = {
    "1hr": 18.0,
    "6hr": 14.0,
    "1d": 10.0,
    "3d": 12.0,
    "7d": 15.0,
}

FLAT_RETRY_COST = 10.0


def run_retry_cost_sensitivity():
    input_path = PROJECT_ROOT / "audit" / "evaluation_results" / "phase1" / "phase1_per_seed_results.json"
    if not input_path.exists():
        raise FileNotFoundError(f"Canonical Phase 1 results not found at: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    # Recompute metrics for each seed & policy
    processed_records = []
    by_policy_orig = {}
    by_policy_alt = {}
    seed_policy_map_orig = {}
    seed_policy_map_alt = {}

    for r in records:
        seed = r["seed"]
        pname = r["policy_name"]
        gross = r["gross_recovered_revenue"]
        orig_cost = r["total_retry_cost"]
        orig_net = r["net_revenue"]

        c_1hr = r.get("arm_count_1hr", 0)
        c_6hr = r.get("arm_count_6hr", 0)
        c_1d = r.get("arm_count_1d", 0)
        c_3d = r.get("arm_count_3d", 0)
        c_7d = r.get("arm_count_7d", 0)

        alt_cost = (
            c_1hr * ALTERNATIVE_COST_TABLE["1hr"] +
            c_6hr * ALTERNATIVE_COST_TABLE["6hr"] +
            c_1d * ALTERNATIVE_COST_TABLE["1d"] +
            c_3d * ALTERNATIVE_COST_TABLE["3d"] +
            c_7d * ALTERNATIVE_COST_TABLE["7d"]
        )
        alt_net = gross - alt_cost

        item = dict(r)
        item["alt_total_retry_cost"] = round(alt_cost, 2)
        item["alt_net_revenue"] = round(alt_net, 2)
        item["cost_delta"] = round(alt_cost - orig_cost, 2)
        item["net_revenue_delta"] = round(alt_net - orig_net, 2)
        processed_records.append(item)

        if pname not in by_policy_orig:
            by_policy_orig[pname] = []
            by_policy_alt[pname] = []
            seed_policy_map_orig[pname] = {}
            seed_policy_map_alt[pname] = {}

        by_policy_orig[pname].append(orig_net)
        by_policy_alt[pname].append(alt_net)
        seed_policy_map_orig[pname][seed] = orig_net
        seed_policy_map_alt[pname][seed] = alt_net

    # Calculate policy averages
    policies = ["RecoverFlow LinUCB", "Fixed Schedule", "Best Static Arm", "Contextual Heuristic", "Ground-Truth Oracle"]
    summary_per_policy = {}

    for p in policies:
        if p in by_policy_orig:
            orig_means = np.mean(by_policy_orig[p])
            alt_means = np.mean(by_policy_alt[p])
            summary_per_policy[p] = {
                "orig_mean_net_revenue": round(float(orig_means), 2),
                "alt_mean_net_revenue": round(float(alt_means), 2),
                "net_revenue_change": round(float(alt_means - orig_means), 2),
                "net_revenue_change_pct": round(float((alt_means - orig_means) / orig_means * 100.0), 2) if orig_means != 0 else 0.0,
            }

    # Calculate paired lift comparison (RecoverFlow vs Baselines)
    target_policy = "RecoverFlow LinUCB"
    baselines = ["Fixed Schedule", "Best Static Arm", "Contextual Heuristic", "Ground-Truth Oracle"]
    lift_comparisons = {}

    seeds = sorted(list(seed_policy_map_orig[target_policy].keys()))

    for b in baselines:
        if b not in seed_policy_map_orig:
            continue

        # Original flat-cost deltas
        orig_deltas = [seed_policy_map_orig[target_policy][s] - seed_policy_map_orig[b][s] for s in seeds]
        orig_mean_lift = float(np.mean(orig_deltas))
        orig_wins = sum(1 for d in orig_deltas if d > 0)

        # Alternative realistic-cost deltas
        alt_deltas = [seed_policy_map_alt[target_policy][s] - seed_policy_map_alt[b][s] for s in seeds]
        alt_mean_lift = float(np.mean(alt_deltas))
        alt_wins = sum(1 for d in alt_deltas if d > 0)

        # Paired bootstrap CI on alternative deltas
        np.random.seed(42)
        boot_means = []
        n_boot = 10000
        for _ in range(n_boot):
            boot_sample = np.random.choice(alt_deltas, size=len(alt_deltas), replace=True)
            boot_means.append(np.mean(boot_sample))
        ci_lower = float(np.percentile(boot_means, 2.5))
        ci_upper = float(np.percentile(boot_means, 97.5))

        lift_comparisons[f"vs_{b.replace(' ', '_')}"] = {
            "baseline_policy": b,
            "orig_flat_cost_mean_lift": round(orig_mean_lift, 2),
            "orig_win_rate": f"{orig_wins}/{len(seeds)} ({orig_wins/len(seeds)*100:.0f}%)",
            "alt_realistic_cost_mean_lift": round(alt_mean_lift, 2),
            "alt_win_rate": f"{alt_wins}/{len(seeds)} ({alt_wins/len(seeds)*100:.0f}%)",
            "alt_lift_change": round(alt_mean_lift - orig_mean_lift, 2),
            "alt_bootstrap_95ci": [round(ci_lower, 2), round(ci_upper, 2)],
        }

    out_dir = PROJECT_ROOT / "audit" / "evaluation_results" / "phase1_retry_cost_sensitivity"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "retry_cost_sensitivity_results.json"

    result_payload = {
        "analysis_name": "Phase 1 Retry Cost Realism Post-Hoc Sensitivity Analysis",
        "description": "Evaluates Phase 1 benchmark net revenue under realistic per-arm cost table without modifying canonical pipeline.",
        "alternative_cost_table_inr": ALTERNATIVE_COST_TABLE,
        "flat_retry_cost_baseline_inr": FLAT_RETRY_COST,
        "policy_net_revenue_summary": summary_per_policy,
        "recoverflow_paired_lift_comparison": lift_comparisons,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result_payload, f, indent=2)

    # Print clean stdout table
    print("====================================================================================================")
    print("RECOVERFLOW PHASE 1 RETRY COST REALISM SENSITIVITY ANALYSIS")
    print("====================================================================================================")
    print(f"Alternative Cost Table (INR): {ALTERNATIVE_COST_TABLE}\n")

    print(f"{'Policy Name':<25} | {'Original Net Rev':<18} | {'Alt-Cost Net Rev':<18} | {'Net Change (INR)':<18}")
    print("-" * 86)
    for p in policies:
        if p in summary_per_policy:
            m = summary_per_policy[p]
            print(f"{p:<25} | INR {m['orig_mean_net_revenue']:>14,.2f} | INR {m['alt_mean_net_revenue']:>14,.2f} | INR {m['net_revenue_change']:>14,.2f}")

    print("\n----------------------------------------------------------------------------------------------------")
    print("RECOVERFLOW NET LIFT COMPARISON UNDER ALTERNATIVE COST TABLE:")
    print("----------------------------------------------------------------------------------------------------")
    for k, v in lift_comparisons.items():
        b = v["baseline_policy"]
        orig_l = v["orig_flat_cost_mean_lift"]
        alt_l = v["alt_realistic_cost_mean_lift"]
        win = v["alt_win_rate"]
        ci = v["alt_bootstrap_95ci"]
        print(f"vs {b:<21} | Orig Lift: INR +{orig_l:>10,.2f} | Alt Lift: INR +{alt_l:>10,.2f} | Win Rate: {win} | 95% CI: [{ci[0]:,.2f}, {ci[1]:,.2f}]")

    print("====================================================================================================")
    print(f"[PASS] Sensitivity Artifact Saved: {out_file.absolute()}\n")

    return result_payload


if __name__ == "__main__":
    run_retry_cost_sensitivity()
