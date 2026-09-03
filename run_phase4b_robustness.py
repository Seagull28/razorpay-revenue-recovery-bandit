"""
run_phase4b_robustness.py
Phase 4B Robustness Evaluation Execution Harness.

Evaluates LinUCBPolicy vs FixedSchedulePolicy across 3 environmental scenarios:
  1. Baseline Scenario (Reference)
  2. High-NSF Scenario (Insufficient funds increased to 60%)
  3. Distribution-Shift Scenario (Issuer timeout dominant + 30% recovery drop)

Evaluated across 3 seeds [42, 101, 2026] for 3,000 transactions each.
Purely additive evaluation; saves artifacts to audit/evaluation_results/phase4b_robustness/.
"""

import sys
import json
from pathlib import Path
from typing import Any, Dict, List
import numpy as np

# Ensure root path resolution
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

import types
if "bandit_retry_scheduler" not in sys.modules:
    mod = types.ModuleType("bandit_retry_scheduler")
    mod.__path__ = [str(PROJECT_ROOT)]
    sys.modules["bandit_retry_scheduler"] = mod

from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.policies.fixed_schedule import FixedSchedulePolicy
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.config import DEFAULT_RETRY_COST, DELAY_ARMS
from bandit_retry_scheduler.simulator.scenario_config import (
    BASELINE_SCENARIO,
    HIGH_INSUFFICIENT_FUNDS_SCENARIO,
    DISTRIBUTION_SHIFT_SCENARIO,
    ScenarioConfig,
)
from bandit_retry_scheduler.simulator.scenario_environment import (
    ScenarioAwareRetrySimulator,
    ScenarioAwareStreamGenerator,
)

ROBUSTNESS_SEEDS = [42, 101, 2026]
SCENARIOS: List[ScenarioConfig] = [
    BASELINE_SCENARIO,
    HIGH_INSUFFICIENT_FUNDS_SCENARIO,
    DISTRIBUTION_SHIFT_SCENARIO,
]


def run_phase4b_robustness():
    output_dir = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4b_robustness"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("====================================================================================================")
    print("RUNNING RECOVERFLOW PHASE 4B ROBUSTNESS EVALUATION (3 SCENARIOS, 2 POLICIES, 3 SEEDS)")
    print("====================================================================================================\n")

    per_run_results: List[Dict[str, Any]] = []

    for sc in SCENARIOS:
        print(f"--- Running Scenario: {sc.name.upper()} ---")
        for seed in ROBUSTNESS_SEEDS:
            # Policy instances for this seed
            policies_to_evaluate = [
                ("RecoverFlow LinUCB", LinUCBPolicy(alpha=1.0)),
                ("Fixed Schedule", FixedSchedulePolicy()),
            ]

            for pname, policy_inst in policies_to_evaluate:
                gen = ScenarioAwareStreamGenerator(config=sc, seed=seed)
                txs = gen.generate_stream(num_days=30, transactions_per_day=100)

                sim = ScenarioAwareRetrySimulator(config=sc, seed=seed)
                engine = PolicyExecutionEngine(simulator=sim, retry_cost=DEFAULT_RETRY_COST)
                logger = AuditLogger()

                engine.run(txs, policy_inst, logger=logger, evaluation_seed=seed, use_crn=True)

                records = logger.to_records()
                total_txs = len(txs)

                # Compute metrics
                recovered_tx_ids = {r["transaction_id"] for r in records if r["actual_outcome"] == 1}
                rec_count = len(recovered_tx_ids)
                rec_rate_pct = round((rec_count / total_txs) * 100.0, 2) if total_txs > 0 else 0.0

                attempts_count = len(records)
                avg_attempts = round(attempts_count / total_txs, 4) if total_txs > 0 else 0.0

                gross_revenue = float(sum(r["amount_recovered"] for r in records if r["actual_outcome"] == 1))
                total_retry_cost = float(attempts_count * DEFAULT_RETRY_COST)
                net_revenue = round(gross_revenue - total_retry_cost, 2)

                arm_counts = {arm: sum(1 for r in records if r["arm_chosen"] == arm) for arm in DELAY_ARMS}

                run_res = {
                    "scenario_name": sc.name,
                    "scenario_description": sc.description,
                    "seed": seed,
                    "policy_name": pname,
                    "transactions_total": total_txs,
                    "recovered_transactions": rec_count,
                    "recovery_rate_pct": rec_rate_pct,
                    "total_attempts": attempts_count,
                    "average_attempts_per_transaction": avg_attempts,
                    "gross_recovered_revenue": round(gross_revenue, 2),
                    "total_retry_cost": round(total_retry_cost, 2),
                    "net_revenue": net_revenue,
                    "arm_counts": arm_counts,
                }
                per_run_results.append(run_res)

    # Save raw per-run results
    raw_path = output_dir / "phase4b_per_run_results.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(per_run_results, f, indent=2)

    # Compute aggregated summary across 3 seeds
    summary: Dict[str, Any] = {
        "evaluation_phase": "Phase 4B Robustness Evaluation",
        "seeds": ROBUSTNESS_SEEDS,
        "seed_count": len(ROBUSTNESS_SEEDS),
        "scope_notes": "3 seeds evaluated across 2 policies (LinUCB vs Fixed Schedule). Regret metric omitted by design.",
        "scenarios": {},
    }

    print("\n====================================================================================================")
    print("PHASE 4B ROBUSTNESS SUMMARY TABLE (AVERAGED OVER 3 SEEDS)")
    print("====================================================================================================")
    print(f"{'Scenario Name':<25} | {'Policy Name':<20} | {'Rec Rate (%)':<12} | {'Net Revenue (INR)':<18} | {'Avg Attempts':<12}")
    print("-" * 98)

    for sc in SCENARIOS:
        summary["scenarios"][sc.name] = {
            "description": sc.description,
            "policies": {},
        }
        for pname in ["RecoverFlow LinUCB", "Fixed Schedule"]:
            matching = [r for r in per_run_results if r["scenario_name"] == sc.name and r["policy_name"] == pname]
            mean_rec = round(float(np.mean([r["recovery_rate_pct"] for r in matching])), 2)
            mean_net = round(float(np.mean([r["net_revenue"] for r in matching])), 2)
            mean_att = round(float(np.mean([r["average_attempts_per_transaction"] for r in matching])), 4)
            mean_gross = round(float(np.mean([r["gross_recovered_revenue"] for r in matching])), 2)
            mean_cost = round(float(np.mean([r["total_retry_cost"] for r in matching])), 2)

            summary["scenarios"][sc.name]["policies"][pname] = {
                "mean_recovery_rate_pct": mean_rec,
                "mean_net_revenue_inr": mean_net,
                "mean_gross_revenue_inr": mean_gross,
                "mean_retry_cost_inr": mean_cost,
                "mean_average_attempts": mean_att,
            }

            print(f"{sc.name:<25} | {pname:<20} | {mean_rec:>10.2f}% | INR {mean_net:>14,.2f} | {mean_att:>12.4f}")

    # Compute comparative lift per scenario (LinUCB vs Fixed Schedule)
    for sc in SCENARIOS:
        s_lin = summary["scenarios"][sc.name]["policies"]["RecoverFlow LinUCB"]
        s_fix = summary["scenarios"][sc.name]["policies"]["Fixed Schedule"]

        lift_net = round(s_lin["mean_net_revenue_inr"] - s_fix["mean_net_revenue_inr"], 2)
        lift_rec = round(s_lin["mean_recovery_rate_pct"] - s_fix["mean_recovery_rate_pct"], 2)
        summary["scenarios"][sc.name]["lift_vs_fixed_schedule"] = {
            "net_revenue_lift_inr": lift_net,
            "recovery_rate_lift_pct": lift_rec,
        }

    summary_path = output_dir / "phase4b_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n----------------------------------------------------------------------------------------------------")
    print("RECOVERFLOW LINUCB LIFT VS FIXED SCHEDULE PER SCENARIO:")
    print("----------------------------------------------------------------------------------------------------")
    for sc in SCENARIOS:
        l_info = summary["scenarios"][sc.name]["lift_vs_fixed_schedule"]
        print(f"Scenario: {sc.name:<25} | Net Revenue Lift: INR +{l_info['net_revenue_lift_inr']:>12,.2f} | Rec Rate Lift: +{l_info['recovery_rate_lift_pct']:>5.2f}%")

    print("====================================================================================================")
    print(f"[PASS] Raw Results Saved : {raw_path.absolute()}")
    print(f"[PASS] Summary Saved     : {summary_path.absolute()}\n")

    return summary


if __name__ == "__main__":
    run_phase4b_robustness()
