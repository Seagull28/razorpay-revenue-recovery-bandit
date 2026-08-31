"""
run_phase4_evaluation.py
Main entry point for executing Phase 4 formal evaluation harness across seeds 42, 101, and 2026.
Generates evaluation metrics, outputs PNG plots, and produces the consolidated evaluation report.
"""

from pathlib import Path
import sys

# Ensure root directory is in sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir.parent) not in sys.path:
    sys.path.insert(0, str(root_dir.parent))

from bandit_retry_scheduler.evaluation.harness import EvaluationHarness
from bandit_retry_scheduler.evaluation.report_generator import generate_evaluation_report


def main():
    print("=" * 100)
    print("BANDIT-OPTIMIZED RETRY SCHEDULER: PHASE 4 FORMAL EVALUATION RUNNER")
    print("=" * 100)

    base_dir = Path(__file__).resolve().parent
    plots_dir = base_dir / "audit" / "plots"
    report_path = base_dir / "audit" / "evaluation_report.md"

    print(f"\n[1/3] Initializing Evaluation Harness (Seeds: [42, 101, 2026], 30 Days, 3,000 Tx/seed)...")
    harness = EvaluationHarness(seeds=[42, 101, 2026], num_days=30, transactions_per_day=100)

    print("[2/3] Running multi-seed simulations, regret analysis, and generating plots...")
    eval_results = harness.run_full_evaluation(output_plots_dir=str(plots_dir))

    print(f"\nPlots generated in: {plots_dir}")
    for name, path in eval_results["plots_generated"].items():
        print(f"  - {name}: {path}")

    print(f"\n[3/3] Compiling Section 9 Markdown Evaluation Report...")
    report_content = generate_evaluation_report(
        eval_results=eval_results,
        output_report_path=str(report_path),
        plots_relative_dir="plots",
    )

    print(f"Report saved to: {report_path}")

    # Also save a copy to the brain artifact directory for convenience
    artifact_report_path = Path(r"C:\Users\Thanujha\.gemini\antigravity\brain\30eeb98e-59ae-47b5-85ad-a23d7f580f5a\evaluation_report.md")
    with open(artifact_report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"Artifact report saved to: {artifact_report_path}")

    # Print Executive Summary to terminal
    summary = eval_results["multi_seed_summary"]
    print("\n" + "=" * 100)
    print("EXECUTION SUMMARY")
    print("=" * 100)
    print(f"Baseline Net Revenue Mean : INR {summary['baseline_net_revenue_mean']:,.2f} +/- {summary['baseline_net_revenue_std']:,.2f}")
    print(f"LinUCB Net Revenue Mean   : INR {summary['linucb_net_revenue_mean']:,.2f} +/- {summary['linucb_net_revenue_std']:,.2f}")
    print(f"Mean Net Revenue Lift     : +INR {summary['net_revenue_lift_mean']:,.2f} (+{summary['net_revenue_lift_pct_mean']:.2f}%)")
    print(f"Mean Cumulative Regret    : INR {summary['final_cum_regret_mean']:,.2f}")
    print("=" * 100)
    print("Phase 4 evaluation complete!\n")


if __name__ == "__main__":
    main()
