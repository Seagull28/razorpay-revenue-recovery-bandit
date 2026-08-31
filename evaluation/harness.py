"""
harness.py
Formal reusable evaluation harness for running multi-seed benchmarks,
calculating performance metrics, generating regret curves, convergence stats,
cold-start analysis, and drift adaptation metrics.
"""

from typing import Any, Dict, List, Optional
import numpy as np

from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.evaluation.metrics import (
    compute_arm_selection_share,
    compute_cold_start_metrics,
    compute_comparative_lift,
    compute_drift_adaptation_metrics,
    compute_oracle_regret,
    compute_performance_by_segment,
)
from bandit_retry_scheduler.evaluation.plotting import (
    plot_arm_convergence,
    plot_cold_start_comparison,
    plot_drift_adaptation,
    plot_regret_curve,
)
from bandit_retry_scheduler.policies.fixed_schedule import FixedSchedulePolicy
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator


class EvaluationHarness:
    """
    Formal reusable evaluation harness executing policy benchmarks, computing metrics,
    and rendering visualization plots.
    """

    def __init__(
        self,
        seeds: Optional[List[int]] = None,
        num_days: int = 30,
        transactions_per_day: int = 100,
        retry_cost: float = 10.0,
    ):
        self.seeds = seeds or [42, 101, 2026]
        self.num_days = num_days
        self.transactions_per_day = transactions_per_day
        self.retry_cost = retry_cost

    def run_seed_benchmark(self, seed: int) -> Dict[str, Any]:
        """
        Runs the simulation benchmark for a single seed comparing Baseline vs. Canonical LinUCB.
        """
        # 1. Generate stream
        generator = TransactionStreamGenerator(seed=seed)
        transactions = generator.generate_stream(
            num_days=self.num_days,
            transactions_per_day=self.transactions_per_day,
        )

        # 2. Fixed-Schedule Baseline
        sim_base = RetrySimulator(seed=seed)
        pol_base = FixedSchedulePolicy(max_attempts=4)
        eng_base = PolicyExecutionEngine(simulator=sim_base, retry_cost=self.retry_cost)
        log_base = AuditLogger()
        eng_base.run(transactions=transactions, policy=pol_base, logger=log_base)
        base_records = log_base.to_records()
        base_perf = compute_performance_by_segment(base_records)

        # 3. Canonical LinUCB (min_samples_for_stopping=15, EV stopping rule)
        sim_lin = RetrySimulator(seed=seed)
        pol_lin = LinUCBPolicy(
            alpha=1.0,
            stopping_mode="expected_value",
            min_samples_for_stopping=15,
            max_attempts=4,
            retry_cost=self.retry_cost,
        )
        eng_lin = PolicyExecutionEngine(simulator=sim_lin, retry_cost=self.retry_cost)
        log_lin = AuditLogger()
        eng_lin.run(transactions=transactions, policy=pol_lin, logger=log_lin)
        lin_records = log_lin.to_records()
        lin_perf = compute_performance_by_segment(lin_records)

        # 4. Comparative Lifts
        lifts = compute_comparative_lift(base_perf, lin_perf)

        # 5. Regret Calculation
        regret_data = compute_oracle_regret(lin_records)

        # 6. Convergence Data for 3 Non-Drifting Representative Pairs
        pair1 = compute_arm_selection_share(lin_records, "issuer_timeout", "Bank C", window_size=40)
        pair2 = compute_arm_selection_share(lin_records, "insufficient_funds", "Bank B", window_size=40)
        pair3 = compute_arm_selection_share(lin_records, "do_not_honor", "Bank A", window_size=40)

        # 7. Cold-Start Quantification (Overall and Decomposed for issuer_timeout)
        cold_start_overall = compute_cold_start_metrics(lin_records, n_tx=100)
        cold_start_timeout = compute_cold_start_metrics(lin_records, n_tx=100, failure_code="issuer_timeout")

        # 8. Drift Adaptation Analysis (Bank D, do_not_honor)
        drift_data = compute_drift_adaptation_metrics(lin_records, bank="Bank D", failure_code="do_not_honor")

        return {
            "seed": seed,
            "baseline_performance": base_perf,
            "linucb_performance": lin_perf,
            "lifts": lifts,
            "regret_data": regret_data,
            "convergence_pairs": [pair1, pair2, pair3],
            "cold_start_data": cold_start_overall,
            "cold_start_timeout_data": cold_start_timeout,
            "drift_data": drift_data,
            "baseline_records": base_records,
            "linucb_records": lin_records,
        }

    def run_full_evaluation(self, output_plots_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes the evaluation pipeline across all specified seeds (42, 101, 2026),
        consolidates metrics, and outputs PNG plots.
        """
        per_seed_results = {}
        for seed in self.seeds:
            per_seed_results[seed] = self.run_seed_benchmark(seed)

        # Compute multi-seed summary metrics across seeds
        multi_seed_summary = self._aggregate_multi_seed(per_seed_results)

        # Generate plots using canonical seed 42
        plots_generated = {}
        if output_plots_dir:
            canonical_res = per_seed_results[42] if 42 in per_seed_results else list(per_seed_results.values())[0]

            plots_generated["regret_curve"] = plot_regret_curve(
                canonical_res["regret_data"],
                f"{output_plots_dir}/regret_curve.png"
            )
            plots_generated["convergence_plots"] = plot_arm_convergence(
                canonical_res["convergence_pairs"],
                f"{output_plots_dir}/convergence_plots.png"
            )
            plots_generated["cold_start_comparison"] = plot_cold_start_comparison(
                canonical_res["cold_start_data"],
                canonical_res["cold_start_timeout_data"],
                f"{output_plots_dir}/cold_start_comparison.png"
            )
            plots_generated["drift_adaptation"] = plot_drift_adaptation(
                canonical_res["drift_data"],
                f"{output_plots_dir}/drift_adaptation.png"
            )

        return {
            "per_seed_results": per_seed_results,
            "multi_seed_summary": multi_seed_summary,
            "plots_generated": plots_generated,
        }

    def _aggregate_multi_seed(self, per_seed_results: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregates baseline vs. LinUCB performance across multiple seeds.
        """
        seed_keys = list(per_seed_results.keys())

        b_rec_rates = [per_seed_results[s]["baseline_performance"]["overall"]["recovery_rate_pct"] for s in seed_keys]
        l_rec_rates = [per_seed_results[s]["linucb_performance"]["overall"]["recovery_rate_pct"] for s in seed_keys]
        rec_lifts = [per_seed_results[s]["lifts"]["overall"]["recovery_rate_lift_abs"] for s in seed_keys]

        b_nets = [per_seed_results[s]["baseline_performance"]["overall"]["net_revenue"] for s in seed_keys]
        l_nets = [per_seed_results[s]["linucb_performance"]["overall"]["net_revenue"] for s in seed_keys]
        net_lifts = [per_seed_results[s]["lifts"]["overall"]["net_revenue_lift_abs"] for s in seed_keys]
        net_lifts_pct = [per_seed_results[s]["lifts"]["overall"]["net_revenue_lift_pct"] for s in seed_keys]

        regrets = [per_seed_results[s]["regret_data"]["final_cum_regret_expected"] for s in seed_keys]

        return {
            "seeds": seed_keys,
            "baseline_recovery_rate_mean": float(np.mean(b_rec_rates)),
            "baseline_recovery_rate_std": float(np.std(b_rec_rates)),
            "linucb_recovery_rate_mean": float(np.mean(l_rec_rates)),
            "linucb_recovery_rate_std": float(np.std(l_rec_rates)),
            "recovery_rate_lift_mean": float(np.mean(rec_lifts)),
            "baseline_net_revenue_mean": float(np.mean(b_nets)),
            "baseline_net_revenue_std": float(np.std(b_nets)),
            "linucb_net_revenue_mean": float(np.mean(l_nets)),
            "linucb_net_revenue_std": float(np.std(l_nets)),
            "net_revenue_lift_mean": float(np.mean(net_lifts)),
            "net_revenue_lift_pct_mean": float(np.mean(net_lifts_pct)),
            "final_cum_regret_mean": float(np.mean(regrets)),
        }
