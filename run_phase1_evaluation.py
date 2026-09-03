"""
run_phase1_evaluation.py
Phase 1 Evaluation Hardening Execution Harness.
Executes paired multi-seed benchmarks across 5 evaluation policies using Common Random Numbers (CRN),
validates static arm selection on held-out validation seeds, computes seed-level bootstrap CIs,
and generates structured raw artifacts and PHASE1_EVALUATION_REPORT.md.
"""

import sys
import os
import json
import csv
import copy
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.evaluation.oracle import OraclePolicy
from bandit_retry_scheduler.policies.fixed_schedule import FixedSchedulePolicy
from bandit_retry_scheduler.policies.heuristic import ContextualHeuristicPolicy
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.policies.static_arm import BestStaticArmPolicy, StaticArmPolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.config import DELAY_ARMS, DEFAULT_RETRY_COST
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator

EVALUATION_VERSION = "Phase1_v1.0"
VALIDATION_SEEDS = [1001, 1002, 1003, 1004, 1005]
BENCHMARK_SEEDS = [42, 101, 2026, 301, 402, 503, 604, 705, 806, 907]


def get_file_sha256(filepath: Path) -> str:
    """Computes SHA256 hash of a source file."""
    if not filepath.exists():
        return "file_not_found"
    return hashlib.sha256(filepath.read_bytes()).hexdigest()[:16]


def compute_evaluation_fingerprint() -> Dict[str, Any]:
    """
    Generates a comprehensive evaluation fingerprint capturing configuration parameters,
    LinUCB hyperparameters, and source code SHA256 hashes.
    """
    critical_files = {
        "ground_truth.py": PROJECT_ROOT / "simulator" / "ground_truth.py",
        "environment.py": PROJECT_ROOT / "simulator" / "environment.py",
        "linucb.py": PROJECT_ROOT / "policies" / "linucb.py",
        "fixed_schedule.py": PROJECT_ROOT / "policies" / "fixed_schedule.py",
        "static_arm.py": PROJECT_ROOT / "policies" / "static_arm.py",
        "heuristic.py": PROJECT_ROOT / "policies" / "heuristic.py",
        "oracle.py": PROJECT_ROOT / "evaluation" / "oracle.py",
        "engine.py": PROJECT_ROOT / "runner" / "engine.py",
    }
    source_hashes = {name: get_file_sha256(path) for name, path in critical_files.items()}

    config_payload = f"{EVALUATION_VERSION}:{VALIDATION_SEEDS}:{BENCHMARK_SEEDS}:{DELAY_ARMS}:{DEFAULT_RETRY_COST}"
    config_hash = hashlib.sha256(config_payload.encode("utf-8")).hexdigest()[:12]

    return {
        "evaluation_version": EVALUATION_VERSION,
        "configuration_hash": config_hash,
        "validation_seeds": VALIDATION_SEEDS,
        "benchmark_seeds": BENCHMARK_SEEDS,
        "delay_arms": DELAY_ARMS,
        "retry_cost": DEFAULT_RETRY_COST,
        "linucb_hyperparameters": {
            "alpha": 1.0,
            "min_samples_for_stopping": 15,
            "feature_dimension": 19,
        },
        "source_hashes": source_hashes,
    }


def validate_and_select_best_static_arm(
    validation_seeds: List[int] = VALIDATION_SEEDS,
    num_days: int = 30,
    tx_per_day: int = 100,
    retry_cost: float = DEFAULT_RETRY_COST,
) -> Tuple[str, Dict[str, Any]]:
    """
    Evaluates all 5 static arms on held-out validation seeds.
    Identifies and freezes the highest mean net-revenue static arm.
    The benchmark evaluation seeds have ZERO influence on this selection.
    """
    arm_totals: Dict[str, float] = {arm: 0.0 for arm in DELAY_ARMS}
    per_seed_arm_results: Dict[str, Dict[int, float]] = {arm: {} for arm in DELAY_ARMS}

    for seed in validation_seeds:
        gen = TransactionStreamGenerator(seed=seed)
        raw_txs = gen.generate_stream(num_days=num_days, transactions_per_day=tx_per_day)

        for arm in DELAY_ARMS:
            txs = copy.deepcopy(raw_txs)
            sim = RetrySimulator(seed=seed)
            pol = StaticArmPolicy(target_arm=arm, max_attempts=4)
            eng = PolicyExecutionEngine(simulator=sim, retry_cost=retry_cost)
            logger = AuditLogger()
            eng.run(txs, pol, logger=logger, evaluation_seed=seed, use_crn=True)

            summary = logger.compute_summary_metrics()
            net_rev = summary["net_revenue"]
            arm_totals[arm] += net_rev
            per_seed_arm_results[arm][seed] = net_rev

    mean_net_revs = {arm: arm_totals[arm] / len(validation_seeds) for arm in DELAY_ARMS}
    best_arm = max(mean_net_revs, key=mean_net_revs.get)

    val_summary = {
        "selection_metric": "mean_net_revenue",
        "validation_seeds": validation_seeds,
        "candidate_arms": DELAY_ARMS,
        "selected_best_static_arm": best_arm,
        "mean_net_revenue_by_arm": mean_net_revs,
        "per_seed_arm_net_revenue": per_seed_arm_results,
    }

    return best_arm, val_summary


def compute_policy_seed_metrics(
    seed: int,
    policy_name: str,
    records: List[Dict[str, Any]],
    tx_count: int,
    fingerprint: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Computes standard raw metrics dictionary matching the required Phase 1 schema,
    including both Retried Recovery Rate and Overall Recovery Rate.
    """
    if not records:
        return {}

    # Extract unique transactions
    tx_ids = set(r["transaction_id"] for r in records)
    transactions_eligible = len(tx_ids)
    transactions_stopped = tx_count - transactions_eligible

    attempts = len(records)
    recoveries = sum(1 for r in records if r["actual_outcome"] == 1)

    # Metric A: Recovery Rate Among Retried Transactions
    recovery_rate_retried = (recoveries / transactions_eligible * 100.0) if transactions_eligible > 0 else 0.0
    # Metric B: Overall Failed-Payment Recovery Rate (Total Entering Stream)
    overall_recovery_rate = (recoveries / tx_count * 100.0) if tx_count > 0 else 0.0

    gross_recovered = sum(r["amount_recovered"] for r in records)
    total_cost = sum(abs(r["reward"] - r["amount_recovered"]) if r["actual_outcome"] == 1 else abs(r["reward"]) for r in records)
    net_revenue = gross_recovered - total_cost

    net_rev_per_tx = net_revenue / tx_count if tx_count > 0 else 0.0
    net_rev_per_elig = net_revenue / transactions_eligible if transactions_eligible > 0 else 0.0
    avg_attempts = attempts / transactions_eligible if transactions_eligible > 0 else 0.0

    arm_counts = {f"arm_count_{arm}": sum(1 for r in records if r["arm_chosen"] == arm) for arm in DELAY_ARMS}

    res = {
        "seed": seed,
        "policy_name": policy_name,
        "transactions_total": tx_count,
        "transactions_eligible": transactions_eligible,
        "transactions_stopped": transactions_stopped,
        "retry_attempts": attempts,
        "recoveries": recoveries,
        "recovery_rate_retried_pct": round(recovery_rate_retried, 2),
        "overall_recovery_rate_pct": round(overall_recovery_rate, 2),
        "gross_recovered_revenue": round(gross_recovered, 2),
        "total_retry_cost": round(total_cost, 2),
        "net_revenue": round(net_revenue, 2),
        "net_revenue_per_transaction": round(net_rev_per_tx, 2),
        "net_revenue_per_eligible_transaction": round(net_rev_per_elig, 2),
        "average_attempts_per_transaction": round(avg_attempts, 2),
        "evaluation_version": EVALUATION_VERSION,
        "configuration_hash": fingerprint["configuration_hash"],
    }
    res.update(arm_counts)
    return res


def compute_paired_bootstrap_ci(
    lin_revs: List[float],
    base_revs: List[float],
    n_resamples: int = 10000,
    ci_level: float = 95.0,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Computes 95% bootstrap confidence interval over paired seed-level deltas.
    delta_seed = LinUCB_net_revenue - baseline_net_revenue
    """
    deltas = np.array(lin_revs) - np.array(base_revs)
    n_seeds = len(deltas)

    rng = np.random.default_rng(seed)
    boot_means = []
    for _ in range(n_resamples):
        sample_indices = rng.choice(n_seeds, size=n_seeds, replace=True)
        boot_means.append(float(np.mean(deltas[sample_indices])))

    alpha_low = (100.0 - ci_level) / 2.0
    alpha_high = 100.0 - alpha_low

    ci_lower = float(np.percentile(boot_means, alpha_low))
    ci_upper = float(np.percentile(boot_means, alpha_high))

    wins = sum(1 for d in deltas if d > 0)
    losses = sum(1 for d in deltas if d < 0)
    ties = sum(1 for d in deltas if d == 0)

    return {
        "mean_paired_delta": float(np.mean(deltas)),
        "median_paired_delta": float(np.median(deltas)),
        "std_paired_delta": float(np.std(deltas, ddof=1)),
        "min_paired_delta": float(np.min(deltas)),
        "max_paired_delta": float(np.max(deltas)),
        "win_count": wins,
        "loss_count": losses,
        "tie_count": ties,
        "win_rate_pct": float(wins / n_seeds * 100.0),
        "bootstrap_resamples": n_resamples,
        "bootstrap_unit": "paired_seed_level_delta",
        "ci_level_pct": ci_level,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
    }


def run_phase1_evaluation(
    benchmark_seeds: List[int] = BENCHMARK_SEEDS,
    num_days: int = 30,
    tx_per_day: int = 100,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Executes complete Phase 1 Evaluation Hardening pipeline.
    """
    out_dir = output_dir or (PROJECT_ROOT / "audit" / "evaluation_results" / "phase1")
    out_dir.mkdir(parents=True, exist_ok=True)

    fingerprint = compute_evaluation_fingerprint()

    print("================================================================================")
    print("PHASE 1 EVALUATION HARDENING — RUNNING BEST STATIC ARM VALIDATION")
    print("================================================================================\n")

    best_static_arm, val_summary = validate_and_select_best_static_arm(
        validation_seeds=VALIDATION_SEEDS,
        num_days=num_days,
        tx_per_day=tx_per_day,
    )
    print(f"✅ Held-Out Validation Complete: Selected Best Static Arm = '{best_static_arm}'")
    print(f"   Validation Mean Net Revenues: {val_summary['mean_net_revenue_by_arm']}\n")

    # Save validation summary artifact
    val_artifact_path = out_dir / "phase1_static_arm_validation.json"
    with open(val_artifact_path, "w", encoding="utf-8") as f:
        json.dump(val_summary, f, indent=2)

    print("================================================================================")
    print(f"PHASE 1 EVALUATION HARDENING — RUNNING {len(benchmark_seeds)}-SEED PAIRED BENCHMARK")
    print("================================================================================\n")

    raw_results: List[Dict[str, Any]] = []
    by_policy_seed_net: Dict[str, Dict[int, float]] = {
        "Fixed Schedule": {},
        "Best Static Arm": {},
        "Contextual Heuristic": {},
        "RecoverFlow LinUCB": {},
        "Ground-Truth Greedy Oracle": {},
    }

    total_tx_per_seed = num_days * tx_per_day

    for seed in benchmark_seeds:
        gen = TransactionStreamGenerator(seed=seed)
        raw_txs = gen.generate_stream(num_days=num_days, transactions_per_day=tx_per_day)

        policies_to_test = [
            ("Fixed Schedule", FixedSchedulePolicy(max_attempts=4)),
            ("Best Static Arm", BestStaticArmPolicy(frozen_arm=best_static_arm, validation_summary=val_summary, max_attempts=4)),
            ("Contextual Heuristic", ContextualHeuristicPolicy(max_attempts=4)),
            ("RecoverFlow LinUCB", LinUCBPolicy(alpha=1.0, min_samples_for_stopping=15, max_attempts=4)),
            ("Ground-Truth Greedy Oracle", OraclePolicy(max_attempts=4)),
        ]

        for p_name, pol_inst in policies_to_test:
            txs_copy = copy.deepcopy(raw_txs)
            sim = RetrySimulator(seed=seed)
            eng = PolicyExecutionEngine(simulator=sim, retry_cost=DEFAULT_RETRY_COST)
            logger = AuditLogger()
            eng.run(txs_copy, pol_inst, logger=logger, evaluation_seed=seed, use_crn=True)

            recs = logger.to_records()
            m = compute_policy_seed_metrics(seed, p_name, recs, total_tx_per_seed, fingerprint)
            raw_results.append(m)
            by_policy_seed_net[p_name][seed] = m["net_revenue"]

    # Compute Summary Table
    summary_by_policy: Dict[str, Dict[str, Any]] = {}
    for p_name in by_policy_seed_net.keys():
        p_metrics = [r for r in raw_results if r["policy_name"] == p_name]
        mean_net = float(np.mean([r["net_revenue"] for r in p_metrics]))
        mean_rec_retried = float(np.mean([r["recovery_rate_retried_pct"] for r in p_metrics]))
        mean_rec_overall = float(np.mean([r["overall_recovery_rate_pct"] for r in p_metrics]))
        mean_cost = float(np.mean([r["total_retry_cost"] for r in p_metrics]))
        mean_attempts = float(np.mean([r["retry_attempts"] for r in p_metrics]))

        summary_by_policy[p_name] = {
            "mean_net_revenue": round(mean_net, 2),
            "mean_recovery_rate_retried_pct": round(mean_rec_retried, 2),
            "mean_overall_recovery_rate_pct": round(mean_rec_overall, 2),
            "mean_retry_cost": round(mean_cost, 2),
            "mean_retry_attempts": round(mean_attempts, 2),
        }

    # Compute Paired Seed Comparisons relative to RecoverFlow LinUCB
    lin_nets = [by_policy_seed_net["RecoverFlow LinUCB"][s] for s in benchmark_seeds]
    oracle_nets = [by_policy_seed_net["Ground-Truth Greedy Oracle"][s] for s in benchmark_seeds]

    paired_comparisons = {
        "RecoverFlow_vs_FixedSchedule": compute_paired_bootstrap_ci(
            lin_nets, [by_policy_seed_net["Fixed Schedule"][s] for s in benchmark_seeds]
        ),
        "RecoverFlow_vs_BestStaticArm": compute_paired_bootstrap_ci(
            lin_nets, [by_policy_seed_net["Best Static Arm"][s] for s in benchmark_seeds]
        ),
        "RecoverFlow_vs_ContextualHeuristic": compute_paired_bootstrap_ci(
            lin_nets, [by_policy_seed_net["Contextual Heuristic"][s] for s in benchmark_seeds]
        ),
        "Oracle_vs_RecoverFlow": compute_paired_bootstrap_ci(
            oracle_nets, lin_nets
        ),
    }

    # Save JSON Raw Per-Seed Artifact
    json_raw_path = out_dir / "phase1_per_seed_results.json"
    with open(json_raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_results, f, indent=2)

    # Save CSV Raw Per-Seed Artifact
    csv_raw_path = out_dir / "phase1_per_seed_results.csv"
    if raw_results:
        keys = list(raw_results[0].keys())
        with open(csv_raw_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(raw_results)

    # Save Summary JSON
    summary_path = out_dir / "phase1_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary_by_policy": summary_by_policy,
            "evaluation_fingerprint": fingerprint,
        }, f, indent=2)

    # Save Paired Comparisons JSON
    paired_path = out_dir / "phase1_paired_comparisons.json"
    with open(paired_path, "w", encoding="utf-8") as f:
        json.dump(paired_comparisons, f, indent=2)

    # Build Markdown Report
    report_text = generate_phase1_markdown_report(
        best_static_arm, val_summary, summary_by_policy, paired_comparisons, raw_results, benchmark_seeds
    )
    report_md_path = out_dir / "PHASE1_EVALUATION_REPORT.md"
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    print("================================================================================")
    print("PHASE 1 EVALUATION HARDENING COMPLETE")
    print("================================================================================")
    print(f"Artifacts Saved to: {out_dir.absolute()}\n")

    return {
        "best_static_arm": best_static_arm,
        "summary_by_policy": summary_by_policy,
        "paired_comparisons": paired_comparisons,
        "fingerprint": fingerprint,
    }


def generate_phase1_markdown_report(
    best_arm: str,
    val_summary: Dict[str, Any],
    summary: Dict[str, Any],
    paired: Dict[str, Any],
    raw_results: List[Dict[str, Any]],
    seeds: List[int],
) -> str:
    """
    Generates human-readable PHASE1_EVALUATION_REPORT.md matching all required sections.
    """
    lines = []
    lines.append("# 🛡️ RecoverFlow Phase 1: Evaluation Hardening Report")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("This document presents the rigorous, fair, and reproducible Phase 1 evaluation benchmark for RecoverFlow. All policies were evaluated under **Common Random Numbers (CRN)** and identical transaction streams across 10 benchmark seeds.")
    lines.append("")

    lines.append("### Policy Performance Summary (10 Benchmark Seeds)")
    lines.append("| Policy Name | Mean Net Revenue (INR) | Retried Rec Rate (%) | Overall Rec Rate (%) | Mean Retry Cost (INR) | Mean Attempts |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
    for p_name, m in summary.items():
        label_prefix = "⭐ " if p_name == "RecoverFlow LinUCB" else ("🔮 " if "Oracle" in p_name else "")
        lines.append(f"| {label_prefix}**{p_name}** | ₹{m['mean_net_revenue']:,.2f} | {m['mean_recovery_rate_retried_pct']:.2f}% | {m['mean_overall_recovery_rate_pct']:.2f}% | ₹{m['mean_retry_cost']:,.2f} | {m['mean_retry_attempts']} |")
    lines.append("")

    lines.append("## 1. Static Arm Validation (Held-Out Seeds)")
    lines.append("To prevent evaluation data leakage, the **Best Static Arm** was selected by evaluating all 5 static arms across 5 held-out validation seeds `[1001, 1002, 1003, 1004, 1005]`. The benchmark seeds had ZERO influence on selection.")
    lines.append("")
    lines.append(f"- **Frozen Selected Arm**: `Always {best_arm}`")
    lines.append(f"- **Selection Metric**: `mean_net_revenue`")
    lines.append("- **Validation Mean Net Revenue Breakdown**:")
    for arm, val_net in val_summary["mean_net_revenue_by_arm"].items():
        sel_mark = " (Selected)" if arm == best_arm else ""
        lines.append(f"  - `Always {arm}`: ₹{val_net:,.2f}{sel_mark}")
    lines.append("")

    lines.append("## 2. Paired Seed-Level Delta Comparisons & Bootstrap CIs")
    lines.append(r"All comparisons represent **paired seed-level deltas** ($\Delta_{\text{seed}} = \text{LinUCB} - \text{Baseline}$) with 10,000 bootstrap resamples.")
    lines.append("")
    lines.append("| Comparison Pair | Mean Lift (INR) | Win Rate | 95% Bootstrap CI |")
    lines.append("| :--- | :---: | :---: | :---: |")

    rf_fix = paired["RecoverFlow_vs_FixedSchedule"]
    rf_stat = paired["RecoverFlow_vs_BestStaticArm"]
    rf_heur = paired["RecoverFlow_vs_ContextualHeuristic"]
    orc_rf = paired["Oracle_vs_RecoverFlow"]

    lines.append(f"| RecoverFlow vs. Fixed Schedule | +₹{rf_fix['mean_paired_delta']:,.2f} | {rf_fix['win_rate_pct']:.1f}% ({rf_fix['win_count']}/10) | [{rf_fix['ci_lower']:+,.2f}, {rf_fix['ci_upper']:+,.2f}] |")
    lines.append(f"| RecoverFlow vs. Best Static Arm (`{best_arm}`) | +₹{rf_stat['mean_paired_delta']:,.2f} | {rf_stat['win_rate_pct']:.1f}% ({rf_stat['win_count']}/10) | [{rf_stat['ci_lower']:+,.2f}, {rf_stat['ci_upper']:+,.2f}] |")
    lines.append(f"| RecoverFlow vs. Contextual Heuristic | +₹{rf_heur['mean_paired_delta']:,.2f} | {rf_heur['win_rate_pct']:.1f}% ({rf_heur['win_count']}/10) | [{rf_heur['ci_lower']:+,.2f}, {rf_heur['ci_upper']:+,.2f}] |")
    lines.append(f"| Ground-Truth Greedy Oracle vs. RecoverFlow | +₹{orc_rf['mean_paired_delta']:,.2f} | N/A (Reference Ceiling) | [{orc_rf['ci_lower']:+,.2f}, {orc_rf['ci_upper']:+,.2f}] |")
    lines.append("")

    lines.append("## 3. Ground-Truth Greedy Oracle Disclaimer")
    lines.append("> [!IMPORTANT]")
    lines.append("> **Ground-Truth Greedy Oracle (Evaluation Only)**: The Oracle uses hidden simulator recovery probabilities and selects the retry action with the highest immediate expected net value for the current decision. It is **evaluation-only** and **not a production policy**. It is a ground-truth reference benchmark, not necessarily a globally optimal sequential policy across the entire retry trajectory. It is **strictly isolated from production decision and policy modules** (`api/`, `policies/`, `runner/`).")

    lines.append("")
    lines.append("## 4. Per-Seed Breakdown (All 10 Benchmark Seeds)")
    lines.append("| Seed | Fixed Schedule (INR) | Best Static (INR) | Heuristic (INR) | RecoverFlow (INR) | Oracle (INR) |")
    lines.append("| :---: | :---: | :---: | :---: | :---: | :---: |")

    for s in seeds:
        f_net = next(r["net_revenue"] for r in raw_results if r["seed"] == s and r["policy_name"] == "Fixed Schedule")
        b_net = next(r["net_revenue"] for r in raw_results if r["seed"] == s and r["policy_name"] == "Best Static Arm")
        h_net = next(r["net_revenue"] for r in raw_results if r["seed"] == s and r["policy_name"] == "Contextual Heuristic")
        l_net = next(r["net_revenue"] for r in raw_results if r["seed"] == s and r["policy_name"] == "RecoverFlow LinUCB")
        o_net = next(r["net_revenue"] for r in raw_results if r["seed"] == s and r["policy_name"] == "Ground-Truth Greedy Oracle")
        lines.append(f"| {s} | ₹{f_net:,.2f} | ₹{b_net:,.2f} | ₹{h_net:,.2f} | ₹{l_net:,.2f} | ₹{o_net:,.2f} |")

    return "\n".join(lines)


if __name__ == "__main__":
    run_phase1_evaluation()
