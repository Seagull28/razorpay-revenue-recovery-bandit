"""
analyze_calibration.py
Decision-Time Probability Estimation & Calibration Analysis for RecoverFlow V2.
Evaluates predicted success probability P_hat(success | x, a) recorded AT ACTUAL DECISION TIME
against actual success outcomes, preventing post-hoc model recomputation leakage.
"""

import sys
from pathlib import Path
import json
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.core.action_registry import ActionRegistry
from bandit_retry_scheduler.core.v2_ev_estimator import V2EVEstimator
from bandit_retry_scheduler.policies.v2_linucb import V2LinUCBPolicy
from bandit_retry_scheduler.run_v2_evaluation import generate_v2_stream, DEFAULT_SEEDS
from bandit_retry_scheduler.compare_ev_impact import DecisionTimeAuditEngine


def main():
    registry = ActionRegistry()
    bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]

    # Population 1: Selected Action Decision-Time Predictions
    sel_bin_counts = [0] * (len(bins) - 1)
    sel_bin_preds = [[] for _ in range(len(bins) - 1)]
    sel_bin_actuals = [[] for _ in range(len(bins) - 1)]

    # Population 2: All Evaluated Candidate Action Decision-Time Predictions
    all_bin_counts = [0] * (len(bins) - 1)
    all_bin_preds = [[] for _ in range(len(bins) - 1)]

    all_snapshots = []

    for seed in DEFAULT_SEEDS:
        stream = generate_v2_stream(seed=seed, num_days=30, tx_per_day=100)
        sim_policy = V2LinUCBPolicy(registry=registry)
        ev_estimator = V2EVEstimator(registry=registry)
        sim_policy.ev_estimator = ev_estimator

        engine = DecisionTimeAuditEngine(registry=registry)
        engine.decision_service.policy = sim_policy
        engine.decision_service.ev_estimator = ev_estimator

        logger = AuditLogger()
        engine.run([dict(tx) for tx in stream], sim_policy, logger=logger, evaluation_seed=seed, use_crn=True)
        all_snapshots.extend(engine.decision_snapshots)

    for snap in all_snapshots:
        # Population 1: Selected / Executed Action
        if snap.get("executed") and snap.get("chosen_action_id"):
            act_id = snap["chosen_action_id"]
            p_hat = snap["chosen_action_p_hat"]
            actual = float(snap["actual_outcome"])

            for i in range(len(bins) - 1):
                if bins[i] <= p_hat < bins[i + 1] or (i == len(bins) - 2 and p_hat == 1.0):
                    sel_bin_counts[i] += 1
                    sel_bin_preds[i].append(p_hat)
                    sel_bin_actuals[i].append(actual)
                    break

        # Population 2: All Evaluated Candidate Actions
        for act_id, p_hat in snap["decision_time_probs"].items():
            for i in range(len(bins) - 1):
                if bins[i] <= p_hat < bins[i + 1] or (i == len(bins) - 2 and p_hat == 1.0):
                    all_bin_counts[i] += 1
                    all_bin_preds[i].append(p_hat)
                    break

    print("=" * 70)
    print("DECISION-TIME PROBABILITY ESTIMATION & CALIBRATION ANALYSIS")
    print("=" * 70)
    print("\n1. SELECTED/EXECUTED ACTION POPULATION (Decision-Time Prediction vs Actual Outcome):")
    print("-" * 70)
    print(f"{'Bin':<12} | {'Count':<8} | {'Mean Pred P':<14} | {'Actual Success Rate':<20}")
    print("-" * 70)
    for i in range(len(bins) - 1):
        b_label = f"{bins[i]:.1f}–{bins[i+1]:.1f}"
        cnt = sel_bin_counts[i]
        if cnt > 0:
            mean_p = float(np.mean(sel_bin_preds[i]))
            actual_rate = float(np.mean(sel_bin_actuals[i]))
            print(f"{b_label:<12} | {cnt:<8} | {mean_p:<14.4f} | {actual_rate:<20.4f}")
        else:
            print(f"{b_label:<12} | {cnt:<8} | N/A            | N/A")
    print("-" * 70)

    print("\n2. ALL EVALUATED ELIGIBLE CANDIDATE ACTIONS POPULATION (Decision-Time):")
    print("-" * 70)
    print(f"{'Bin':<12} | {'Count':<8} | {'Mean Pred P':<14}")
    print("-" * 70)
    for i in range(len(bins) - 1):
        b_label = f"{bins[i]:.1f}–{bins[i+1]:.1f}"
        cnt = all_bin_counts[i]
        if cnt > 0:
            mean_p = float(np.mean(all_bin_preds[i]))
            print(f"{b_label:<12} | {cnt:<8} | {mean_p:<14.4f}")
        else:
            print(f"{b_label:<12} | {cnt:<8} | N/A")
    print("-" * 70)


if __name__ == "__main__":
    main()
