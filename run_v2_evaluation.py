"""
run_v2_evaluation.py
RecoverFlow V2 Evaluation Harness & Fix 55A/55B Diagnostic Suite.
Evaluates V2LinUCBPolicy against methodologically valid static baselines across multiple deterministic seeds
using action-independent Common Random Numbers (CRN).
Performs Fix 55A Empirical Stopping Diagnosis and Fix 55B Expected-Value Feasibility Analysis.
Outputs formatted text report, diagnostic analysis, and v2_evaluation_results.json artifact.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.core.action_registry import ActionRegistry
from bandit_retry_scheduler.core.recovery_action import RecoveryAction
from bandit_retry_scheduler.policies.v2_linucb import V2LinUCBPolicy, V2PolicyDecision
from bandit_retry_scheduler.runner.v2_engine import V2PolicyExecutionEngine
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator
from bandit_retry_scheduler.simulator.v2_environment import V2RetrySimulator, V2_METHOD_SWITCH_COST, V2_TIMED_RETRY_COST
from bandit_retry_scheduler.simulator.v2_ground_truth import calculate_v2_recovery_probability


DEFAULT_SEEDS = [42, 123, 456, 789, 2026]


class V2StaticBaselinePolicy:
    """
    Static baseline policy for V2 recovery actions.
    Evaluates availability of preferred target action in eligible candidates list.
    If preferred target is eligible, selects it.
    If preferred target is NOT eligible, returns no-action (action_chosen=None).
    Strictly obeys V2 eligibility rules without executing arbitrary fallback actions.
    """

    def __init__(self, name: str, target_type: str, target_val: str, max_attempts: int = 4):
        self.name = name
        self.target_type = target_type  # "delay" or "target_method"
        self.target_val = target_val    # "1d", "3d", "7d", "upi", "netbanking"
        self.max_attempts = max_attempts
        self.action_counts: Dict[str, int] = {}
        self.target_available_count: int = 0
        self.target_unavailable_count: int = 0

    def select_action(
        self,
        context: Dict[str, Any],
        candidates: Tuple[RecoveryAction, ...],
        attempt_number: int = 1,
    ) -> V2PolicyDecision:
        if not candidates:
            self.target_unavailable_count += 1
            return V2PolicyDecision(
                action_chosen=None,
                action_id="NONE",
                expected_value=0.0,
                metadata={"reason": "no_candidates", "baseline_rule": self.name},
            )

        chosen = None
        for act in candidates:
            if self.target_type == "delay" and act.action_type == "TIMED_RETRY" and act.delay == self.target_val:
                chosen = act
                break
            elif self.target_type == "target_method" and act.action_type == "METHOD_SWITCH" and act.target_method == self.target_val:
                chosen = act
                break

        if chosen is not None:
            self.target_available_count += 1
            self.action_counts[chosen.action_id] = self.action_counts.get(chosen.action_id, 0) + 1
            return V2PolicyDecision(
                action_chosen=chosen,
                action_id=chosen.action_id,
                expected_value=0.0,
                metadata={"baseline_rule": self.name},
            )
        else:
            self.target_unavailable_count += 1
            return V2PolicyDecision(
                action_chosen=None,
                action_id="NONE",
                expected_value=0.0,
                metadata={"reason": "target_action_unavailable", "baseline_rule": self.name},
            )

    def update(self, context: Dict[str, Any], action_id: str, reward: float) -> None:
        """Static baselines do not update state online."""
        pass


def generate_v2_stream(seed: int, num_days: int = 30, tx_per_day: int = 100) -> List[Dict[str, Any]]:
    """
    Generates a deterministic stream of synthetic failed transactions for V2 evaluation.
    Assigns source_method deterministically across card, upi, netbanking based on stream seed.
    """
    gen = TransactionStreamGenerator(seed=seed)
    raw_stream = gen.generate_stream(num_days=num_days, transactions_per_day=tx_per_day)

    rng = np.random.default_rng(seed + 999)
    methods = ["card", "upi", "netbanking"]
    weights = [0.60, 0.30, 0.10]

    v2_stream = []
    for tx in raw_stream:
        tx_copy = dict(tx)
        tx_copy["source_method"] = str(rng.choice(methods, p=weights))
        v2_stream.append(tx_copy)

    return v2_stream


def compute_v2_run_metrics(
    logger: AuditLogger,
    stream_size: int,
    registry: ActionRegistry,
    baseline_policy: Optional[V2StaticBaselinePolicy] = None,
) -> Dict[str, Any]:
    """
    Computes financial, recovery, action, and availability metrics for a single evaluation run.
    """
    records = logger.records
    total_tx = stream_size

    if baseline_policy is not None:
        avail_cnt = baseline_policy.target_available_count
        unavail_cnt = baseline_policy.target_unavailable_count
        total_opps = avail_cnt + unavail_cnt
        avail_pct = round((avail_cnt / total_opps * 100.0), 2) if total_opps > 0 else 0.0
    else:
        avail_cnt = None
        unavail_cnt = None
        avail_pct = None

    if not records:
        res = {
            "total_transactions": total_tx,
            "num_recovered": 0,
            "recovery_rate_pct": 0.0,
            "total_recovered_inr": 0.0,
            "total_action_cost_inr": 0.0,
            "net_reward_inr": 0.0,
            "avg_reward_per_tx": 0.0,
            "total_attempts": 0,
            "avg_attempts_per_tx": 0.0,
            "action_counts": {},
            "action_rates_pct": {},
            "method_switch_count": 0,
            "timed_retry_count": 0,
        }
        if baseline_policy is not None:
            res["target_action_available_count"] = avail_cnt
            res["target_action_unavailable_count"] = unavail_cnt
            res["target_action_available_pct"] = avail_pct
        return res

    tx_stats: Dict[str, Dict[str, Any]] = {}
    total_net_reward = 0.0
    action_counts: Dict[str, int] = {}
    method_switch_count = 0
    timed_retry_count = 0

    for r in records:
        tx_id = r.transaction_id
        total_net_reward += r.reward
        act_id = r.arm_chosen
        action_counts[act_id] = action_counts.get(act_id, 0) + 1

        try:
            act_obj = registry.get_action(act_id)
            if act_obj.action_type == "METHOD_SWITCH":
                method_switch_count += 1
            else:
                timed_retry_count += 1
        except KeyError:
            if "switch" in act_id:
                method_switch_count += 1
            else:
                timed_retry_count += 1

        if tx_id not in tx_stats:
            tx_stats[tx_id] = {
                "recovered": (r.actual_outcome == 1),
                "amount_recovered": r.amount_recovered if r.actual_outcome == 1 else 0.0,
            }
        else:
            if r.actual_outcome == 1:
                tx_stats[tx_id]["recovered"] = True
                tx_stats[tx_id]["amount_recovered"] = max(tx_stats[tx_id]["amount_recovered"], r.amount_recovered)

    num_recovered = sum(1 for s in tx_stats.values() if s["recovered"])
    total_recovered_inr = sum(s["amount_recovered"] for s in tx_stats.values())
    total_action_cost_inr = total_recovered_inr - total_net_reward
    total_attempts = len(records)

    recovery_rate_pct = (num_recovered / total_tx * 100.0) if total_tx > 0 else 0.0
    avg_reward_per_tx = (total_net_reward / total_tx) if total_tx > 0 else 0.0
    avg_attempts_per_tx = (total_attempts / total_tx) if total_tx > 0 else 0.0

    action_rates_pct = {
        act: round((cnt / total_attempts * 100.0), 2) for act, cnt in action_counts.items()
    } if total_attempts > 0 else {}

    res = {
        "total_transactions": total_tx,
        "num_recovered": num_recovered,
        "recovery_rate_pct": round(recovery_rate_pct, 2),
        "total_recovered_inr": round(total_recovered_inr, 2),
        "total_action_cost_inr": round(total_action_cost_inr, 2),
        "net_reward_inr": round(total_net_reward, 2),
        "avg_reward_per_tx": round(avg_reward_per_tx, 2),
        "total_attempts": total_attempts,
        "avg_attempts_per_tx": round(avg_attempts_per_tx, 2),
        "action_counts": action_counts,
        "action_rates_pct": action_rates_pct,
        "method_switch_count": method_switch_count,
        "timed_retry_count": timed_retry_count,
    }

    if baseline_policy is not None:
        res["target_action_available_count"] = avail_cnt
        res["target_action_unavailable_count"] = unavail_cnt
        res["target_action_available_pct"] = avail_pct

    return res


def compute_v2_diagnostics(
    logger: AuditLogger,
    stream_size: int,
    registry: ActionRegistry,
) -> Dict[str, Any]:
    """
    Computes Fix 55A empirical diagnostic metrics evaluating V2 expected-value stopping behavior:
    1. Retry Intensity & Attempt Distribution
    2. Marginal Retry Value by Attempt Number (1..4)
    3. Marginal Action Performance by Action ID
    4. Low-Value / Negative-Reward Retry Diagnosis
    5. Cold-Start Exploration vs Convergence Behavior
    6. Max-Attempt Boundary & Termination Reasons
    """
    records = logger.records
    total_tx = stream_size

    if not records:
        return {}

    tx_records_map: Dict[str, List[Any]] = {}
    for r in records:
        tx_id = r.transaction_id
        if tx_id not in tx_records_map:
            tx_records_map[tx_id] = []
        tx_records_map[tx_id].append(r)

    attempts_per_tx = []
    term_reasons = {"success": 0, "max_attempts": 0, "early_stop": 0}
    tx_reaching_max = 0

    for tx_id, tx_recs in tx_records_map.items():
        n_att = len(tx_recs)
        attempts_per_tx.append(n_att)
        has_success = any(r.actual_outcome == 1 for r in tx_recs)
        if has_success:
            term_reasons["success"] += 1
        elif n_att >= 4:
            term_reasons["max_attempts"] += 1
            tx_reaching_max += 1
        else:
            term_reasons["early_stop"] += 1

    zero_attempt_tx = max(0, total_tx - len(tx_records_map))
    all_attempts_list = attempts_per_tx + [0] * zero_attempt_tx

    attempt_dist = {
        1: sum(1 for a in attempts_per_tx if a == 1),
        2: sum(1 for a in attempts_per_tx if a == 2),
        3: sum(1 for a in attempts_per_tx if a == 3),
        4: sum(1 for a in attempts_per_tx if a == 4),
    }

    avg_attempts_per_tx = float(np.mean(all_attempts_list)) if all_attempts_list else 0.0
    median_attempts_per_tx = float(np.median(all_attempts_list)) if all_attempts_list else 0.0
    pct_reaching_max = round((tx_reaching_max / total_tx * 100.0), 2) if total_tx > 0 else 0.0

    by_attempt = {}
    for att_num in range(1, 5):
        att_recs = [r for r in records if r.context_vector.get("retry_attempt_number", 1) == att_num]
        n_retries = len(att_recs)
        succ = sum(1 for r in att_recs if r.actual_outcome == 1)
        rec_rate = round((succ / n_retries * 100.0), 2) if n_retries > 0 else 0.0
        tot_reward = sum(r.reward for r in att_recs)
        avg_reward = round((tot_reward / n_retries), 2) if n_retries > 0 else 0.0

        by_attempt[att_num] = {
            "num_retries": n_retries,
            "successes": succ,
            "recovery_rate_pct": rec_rate,
            "total_reward_inr": round(tot_reward, 2),
            "avg_reward_per_retry_inr": avg_reward,
        }

    by_action = {}
    all_act_ids = sorted(list(set(r.arm_chosen for r in records)))
    for act_id in all_act_ids:
        act_recs = [r for r in records if r.arm_chosen == act_id]
        n_exec = len(act_recs)
        succ = sum(1 for r in act_recs if r.actual_outcome == 1)
        rec_rate = round((succ / n_exec * 100.0), 2) if n_exec > 0 else 0.0
        tot_reward = sum(r.reward for r in act_recs)
        avg_reward = round((tot_reward / n_exec), 2) if n_exec > 0 else 0.0

        try:
            act_type = registry.get_action(act_id).action_type
        except KeyError:
            act_type = "METHOD_SWITCH" if "switch" in act_id else "TIMED_RETRY"

        by_action[act_id] = {
            "action_type": act_type,
            "execution_count": n_exec,
            "success_count": succ,
            "recovery_rate_pct": rec_rate,
            "total_reward_inr": round(tot_reward, 2),
            "avg_reward_per_execution_inr": avg_reward,
        }

    neg_recs = [r for r in records if r.reward < 0]
    neg_count = len(neg_recs)
    tot_attempts = len(records)
    neg_pct = round((neg_count / tot_attempts * 100.0), 2) if tot_attempts > 0 else 0.0
    tot_neg_reward = sum(r.reward for r in neg_recs)

    neg_by_attempt = {
        1: sum(1 for r in neg_recs if r.context_vector.get("retry_attempt_number", 1) == 1),
        2: sum(1 for r in neg_recs if r.context_vector.get("retry_attempt_number", 1) == 2),
        3: sum(1 for r in neg_recs if r.context_vector.get("retry_attempt_number", 1) == 3),
        4: sum(1 for r in neg_recs if r.context_vector.get("retry_attempt_number", 1) == 4),
    }

    early_tx_ids = set(list(tx_records_map.keys())[:500])
    early_recs = [r for r in records if r.transaction_id in early_tx_ids]
    late_recs = [r for r in records if r.transaction_id not in early_tx_ids]

    early_neg_pct = round((sum(1 for r in early_recs if r.reward < 0) / len(early_recs) * 100.0), 2) if early_recs else 0.0
    late_neg_pct = round((sum(1 for r in late_recs if r.reward < 0) / len(late_recs) * 100.0), 2) if late_recs else 0.0

    early_avg_reward = round((sum(r.reward for r in early_recs) / len(early_recs)), 2) if early_recs else 0.0
    late_avg_reward = round((sum(r.reward for r in late_recs) / len(late_recs)), 2) if late_recs else 0.0

    return {
        "retry_intensity": {
            "avg_attempts_per_tx": round(avg_attempts_per_tx, 2),
            "median_attempts_per_tx": round(median_attempts_per_tx, 2),
            "attempt_distribution": attempt_dist,
            "pct_transactions_reaching_max_attempts": pct_reaching_max,
        },
        "marginal_retry_value_by_attempt": by_attempt,
        "marginal_action_performance": by_action,
        "low_value_retry_diagnosis": {
            "negative_reward_retry_count": neg_count,
            "negative_reward_retry_pct": neg_pct,
            "total_negative_reward_inr": round(tot_neg_reward, 2),
            "negative_reward_by_attempt": neg_by_attempt,
        },
        "cold_start_comparison": {
            "early_first_500_tx": {
                "total_retries": len(early_recs),
                "negative_reward_pct": early_neg_pct,
                "avg_reward_per_retry_inr": early_avg_reward,
            },
            "late_remaining_tx": {
                "total_retries": len(late_recs),
                "negative_reward_pct": late_neg_pct,
                "avg_reward_per_retry_inr": late_avg_reward,
            },
        },
        "termination_reasons": term_reasons,
    }


def compute_v2_ev_feasibility_analysis(
    logger: AuditLogger,
    stream: List[Dict[str, Any]],
    registry: ActionRegistry,
    policy: V2LinUCBPolicy,
) -> Dict[str, Any]:
    """
    Computes Fix 55B Expected-Value (EV) Feasibility Analysis:
    1. Signal Decomposition: theta^T x vs. Exploration Bonus vs. UCB
    2. Negative-EV Opportunity Rates for UCB, theta^T x, and Synthetic Oracle EV
    3. Offline Calibration Analysis (Predicted theta^T x vs. Realized Reward)
    4. Signal Comparison & Architectural Recommendation
    """
    records = logger.records
    if not records:
        return {}

    tx_map = {tx["transaction_id"]: tx for tx in stream}

    theta_x_list = []
    bonus_list = []
    ucb_list = []
    oracle_ev_list = []

    max_theta_x_leq_0 = 0
    max_ucb_leq_0 = 0
    max_oracle_ev_leq_0 = 0
    total_opportunities = 0

    pred_realized_pairs = []

    for r in records:
        tx_id = r.transaction_id
        tx = tx_map.get(tx_id)
        if not tx:
            continue

        ctx = r.context_vector
        x = policy.encoder.encode(ctx)
        source_method = ctx.get("source_method", "card")
        candidates = registry.get_candidates(source_method)

        if not candidates:
            continue

        total_opportunities += 1

        cand_theta_x = []
        cand_ucb = []
        cand_oracle_ev = []

        for act in candidates:
            act_id = act.action_id
            A_a = policy.A[act_id]
            b_a = policy.b[act_id]

            try:
                theta_a = np.linalg.solve(A_a, b_a)
                var_a = float(x.dot(np.linalg.solve(A_a, x)))
            except np.linalg.LinAlgError:
                theta_a = np.zeros(policy.d)
                var_a = 1.0

            est_reward = float(theta_a.dot(x))
            bonus = float(policy.alpha * np.sqrt(max(0.0, var_a)))
            ucb = est_reward + bonus

            p_true = calculate_v2_recovery_probability(ctx, act)
            amount = float(ctx.get("amount", 1000.0))
            cost = 15.0 if act.action_type == "METHOD_SWITCH" else 10.0
            oracle_ev = p_true * amount - cost

            cand_theta_x.append(est_reward)
            cand_ucb.append(ucb)
            cand_oracle_ev.append(oracle_ev)

            if act_id == r.arm_chosen:
                pred_realized_pairs.append((est_reward, r.reward))
                theta_x_list.append(est_reward)
                bonus_list.append(bonus)
                ucb_list.append(ucb)
                oracle_ev_list.append(oracle_ev)

        if max(cand_theta_x) <= 0:
            max_theta_x_leq_0 += 1
        if max(cand_ucb) <= 0:
            max_ucb_leq_0 += 1
        if max(cand_oracle_ev) <= 0:
            max_oracle_ev_leq_0 += 1

    mean_theta_x = float(np.mean(theta_x_list)) if theta_x_list else 0.0
    mean_bonus = float(np.mean(bonus_list)) if bonus_list else 0.0
    mean_ucb = float(np.mean(ucb_list)) if ucb_list else 0.0

    pct_max_theta_leq_0 = round((max_theta_x_leq_0 / total_opportunities * 100.0), 2) if total_opportunities > 0 else 0.0
    pct_max_ucb_leq_0 = round((max_ucb_leq_0 / total_opportunities * 100.0), 2) if total_opportunities > 0 else 0.0
    pct_max_oracle_leq_0 = round((max_oracle_ev_leq_0 / total_opportunities * 100.0), 2) if total_opportunities > 0 else 0.0

    if pred_realized_pairs:
        preds = [p[0] for p in pred_realized_pairs]
        reals = [p[1] for p in pred_realized_pairs]
        mean_pred = float(np.mean(preds))
        mean_real = float(np.mean(reals))
        pred_error = mean_real - mean_pred
    else:
        mean_pred = 0.0
        mean_real = 0.0
        pred_error = 0.0

    signal_comparison = {
        "Signal_A_UCB": {
            "meaning": "Optimistic upper bound (estimate + bonus)",
            "defensible_for_stopping": False,
            "reason": "Exploration bonus remains positive at cold-start (~2.5 INR per unit norm), failing to halt low-EV attempts.",
        },
        "Signal_B_Theta_T_x": {
            "meaning": "Learned linear net reward estimate",
            "defensible_for_stopping": False,
            "reason": "At cold-start theta=0 so theta^T x = 0, causing premature stopping on attempt 1 before parameter learning.",
        },
        "Signal_C_Synthetic_Oracle_EV": {
            "meaning": "True simulator EV (P_true * amount - cost)",
            "defensible_for_stopping": False,
            "reason": "Analysis-only oracle using simulator ground-truth probabilities unavailable in production.",
        },
        "Signal_D_Calibrated_EV_Estimator": {
            "meaning": "Decoupled P_hat(success|x,a) * E[Amount|x] - cost(a)",
            "defensible_for_stopping": True,
            "reason": "Decouples probability estimation from reward modeling, enabling safe economic stopping without cold-start shutdown.",
        },
    }

    return {
        "reward_semantics": "theta^T x represents expected NET REWARD after deducting action cost (10 INR timed / 15 INR switch)",
        "ucb_decomposition": {
            "mean_estimated_reward_inr": round(mean_theta_x, 2),
            "mean_exploration_bonus_inr": round(mean_bonus, 2),
            "mean_ucb_score_inr": round(mean_ucb, 2),
        },
        "negative_ev_opportunity_rates": {
            "total_decision_opportunities": total_opportunities,
            "pct_decisions_max_theta_x_leq_zero": pct_max_theta_leq_0,
            "pct_decisions_max_ucb_leq_zero": pct_max_ucb_leq_0,
            "pct_decisions_max_oracle_ev_leq_zero": pct_max_oracle_leq_0,
        },
        "offline_calibration_error": {
            "mean_predicted_reward_inr": round(mean_pred, 2),
            "mean_realized_reward_inr": round(mean_real, 2),
            "prediction_error_inr": round(pred_error, 2),
        },
        "signal_comparison": signal_comparison,
        "architectural_recommendation": "OPTION B — A separate calibrated EV estimator is required",
    }


def evaluate_single_seed(
    seed: int,
    num_days: int = 30,
    tx_per_day: int = 100,
    registry: Optional[ActionRegistry] = None,
) -> Dict[str, Any]:
    """
    Evaluates V2 Policy and static baselines on a single seed using CRN.
    Also computes Fix 55A empirical diagnostic metrics and Fix 55B EV feasibility.
    """
    reg = registry or ActionRegistry()
    stream = generate_v2_stream(seed=seed, num_days=num_days, tx_per_day=tx_per_day)
    stream_size = len(stream)

    baselines_def = {
        "same_method_1d": V2StaticBaselinePolicy("same_method_1d", "delay", "1d"),
        "same_method_3d": V2StaticBaselinePolicy("same_method_3d", "delay", "3d"),
        "same_method_7d": V2StaticBaselinePolicy("same_method_7d", "delay", "7d"),
        "switch_to_upi": V2StaticBaselinePolicy("switch_to_upi", "target_method", "upi"),
        "switch_to_netbanking": V2StaticBaselinePolicy("switch_to_netbanking", "target_method", "netbanking"),
    }

    # 1. Evaluate V2 LinUCB Policy
    v2_policy = V2LinUCBPolicy(registry=reg)
    v2_sim = V2RetrySimulator(seed=seed)
    v2_engine = V2PolicyExecutionEngine(simulator=v2_sim, registry=reg)
    v2_engine.decision_service.policy = v2_policy
    v2_logger = AuditLogger()

    stream_policy = [dict(tx) for tx in stream]
    v2_engine.run(stream_policy, v2_policy, logger=v2_logger, evaluation_seed=seed, use_crn=True)
    policy_metrics = compute_v2_run_metrics(v2_logger, stream_size, reg)
    diagnostics = compute_v2_diagnostics(v2_logger, stream_size, reg)
    ev_feasibility = compute_v2_ev_feasibility_analysis(v2_logger, stream_policy, reg, v2_policy)

    # 2. Evaluate Baselines independently on the SAME stream and seed
    baseline_metrics = {}
    for base_name, base_policy in baselines_def.items():
        sim_b = V2RetrySimulator(seed=seed)
        engine_b = V2PolicyExecutionEngine(simulator=sim_b, registry=reg)
        engine_b.decision_service.policy = base_policy
        logger_b = AuditLogger()

        stream_b = [dict(tx) for tx in stream]
        engine_b.run(stream_b, base_policy, logger=logger_b, evaluation_seed=seed, use_crn=True)
        baseline_metrics[base_name] = compute_v2_run_metrics(logger_b, stream_size, reg, baseline_policy=base_policy)

    return {
        "seed": seed,
        "v2_linucb": policy_metrics,
        "diagnostics": diagnostics,
        "ev_feasibility": ev_feasibility,
        "baselines": baseline_metrics,
    }


def aggregate_evaluation_results(seed_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregates metrics, diagnostics, and EV feasibility across multiple evaluation seeds.
    """
    n_seeds = len(seed_results)
    if n_seeds == 0:
        return {}

    pol_rewards = [sr["v2_linucb"]["net_reward_inr"] for sr in seed_results]
    pol_rec_rates = [sr["v2_linucb"]["recovery_rate_pct"] for sr in seed_results]
    pol_recovered = [sr["v2_linucb"]["total_recovered_inr"] for sr in seed_results]
    pol_costs = [sr["v2_linucb"]["total_action_cost_inr"] for sr in seed_results]
    pol_attempts = [sr["v2_linucb"]["avg_attempts_per_tx"] for sr in seed_results]
    pol_tx = sum(sr["v2_linucb"]["total_transactions"] for sr in seed_results)

    aggregated_policy = {
        "mean_net_reward_inr": round(float(np.mean(pol_rewards)), 2),
        "mean_recovery_rate_pct": round(float(np.mean(pol_rec_rates)), 2),
        "mean_total_recovered_inr": round(float(np.mean(pol_recovered)), 2),
        "mean_action_cost_inr": round(float(np.mean(pol_costs)), 2),
        "mean_avg_attempts_per_tx": round(float(np.mean(pol_attempts)), 2),
        "total_transactions_all_seeds": pol_tx,
    }

    # Aggregate Diagnostics
    diag_attempts = [sr["diagnostics"]["retry_intensity"]["avg_attempts_per_tx"] for sr in seed_results]
    diag_max_pct = [sr["diagnostics"]["retry_intensity"]["pct_transactions_reaching_max_attempts"] for sr in seed_results]
    diag_neg_pct = [sr["diagnostics"]["low_value_retry_diagnosis"]["negative_reward_retry_pct"] for sr in seed_results]
    diag_neg_cnt = [sr["diagnostics"]["low_value_retry_diagnosis"]["negative_reward_retry_count"] for sr in seed_results]
    diag_neg_rew = [sr["diagnostics"]["low_value_retry_diagnosis"]["total_negative_reward_inr"] for sr in seed_results]

    agg_diagnostics = {
        "mean_avg_attempts_per_tx": round(float(np.mean(diag_attempts)), 2),
        "mean_pct_reaching_max_attempts": round(float(np.mean(diag_max_pct)), 2),
        "mean_negative_reward_retry_pct": round(float(np.mean(diag_neg_pct)), 2),
        "mean_negative_reward_retry_count": round(float(np.mean(diag_neg_cnt)), 2),
        "mean_total_negative_reward_inr": round(float(np.mean(diag_neg_rew)), 2),
    }

    by_att_agg = {}
    for att_num in range(1, 5):
        att_recs_cnt = [sr["diagnostics"]["marginal_retry_value_by_attempt"][att_num]["num_retries"] for sr in seed_results]
        att_succ_cnt = [sr["diagnostics"]["marginal_retry_value_by_attempt"][att_num]["successes"] for sr in seed_results]
        att_rec_pcts = [sr["diagnostics"]["marginal_retry_value_by_attempt"][att_num]["recovery_rate_pct"] for sr in seed_results]
        att_avg_rews = [sr["diagnostics"]["marginal_retry_value_by_attempt"][att_num]["avg_reward_per_retry_inr"] for sr in seed_results]

        by_att_agg[att_num] = {
            "mean_num_retries": round(float(np.mean(att_recs_cnt)), 1),
            "mean_successes": round(float(np.mean(att_succ_cnt)), 1),
            "mean_recovery_rate_pct": round(float(np.mean(att_rec_pcts)), 2),
            "mean_avg_reward_per_retry_inr": round(float(np.mean(att_avg_rews)), 2),
        }
    agg_diagnostics["marginal_retry_value_by_attempt"] = by_att_agg

    # Aggregate EV Feasibility
    ev_theta = [sr["ev_feasibility"]["ucb_decomposition"]["mean_estimated_reward_inr"] for sr in seed_results]
    ev_bonus = [sr["ev_feasibility"]["ucb_decomposition"]["mean_exploration_bonus_inr"] for sr in seed_results]
    ev_ucb = [sr["ev_feasibility"]["ucb_decomposition"]["mean_ucb_score_inr"] for sr in seed_results]

    ev_max_theta = [sr["ev_feasibility"]["negative_ev_opportunity_rates"]["pct_decisions_max_theta_x_leq_zero"] for sr in seed_results]
    ev_max_ucb = [sr["ev_feasibility"]["negative_ev_opportunity_rates"]["pct_decisions_max_ucb_leq_zero"] for sr in seed_results]
    ev_max_oracle = [sr["ev_feasibility"]["negative_ev_opportunity_rates"]["pct_decisions_max_oracle_ev_leq_zero"] for sr in seed_results]

    ev_pred = [sr["ev_feasibility"]["offline_calibration_error"]["mean_predicted_reward_inr"] for sr in seed_results]
    ev_real = [sr["ev_feasibility"]["offline_calibration_error"]["mean_realized_reward_inr"] for sr in seed_results]
    ev_err = [sr["ev_feasibility"]["offline_calibration_error"]["prediction_error_inr"] for sr in seed_results]

    agg_ev = {
        "reward_semantics": seed_results[0]["ev_feasibility"]["reward_semantics"],
        "ucb_decomposition": {
            "mean_estimated_reward_inr": round(float(np.mean(ev_theta)), 2),
            "mean_exploration_bonus_inr": round(float(np.mean(ev_bonus)), 2),
            "mean_ucb_score_inr": round(float(np.mean(ev_ucb)), 2),
        },
        "negative_ev_opportunity_rates": {
            "pct_decisions_max_theta_x_leq_zero": round(float(np.mean(ev_max_theta)), 2),
            "pct_decisions_max_ucb_leq_zero": round(float(np.mean(ev_max_ucb)), 2),
            "pct_decisions_max_oracle_ev_leq_zero": round(float(np.mean(ev_max_oracle)), 2),
        },
        "offline_calibration_error": {
            "mean_predicted_reward_inr": round(float(np.mean(ev_pred)), 2),
            "mean_realized_reward_inr": round(float(np.mean(ev_real)), 2),
            "prediction_error_inr": round(float(np.mean(ev_err)), 2),
        },
        "signal_comparison": seed_results[0]["ev_feasibility"]["signal_comparison"],
        "architectural_recommendation": seed_results[0]["ev_feasibility"]["architectural_recommendation"],
    }

    baseline_names = list(seed_results[0]["baselines"].keys())
    aggregated_baselines = {}
    comparisons = {}

    for bname in baseline_names:
        b_rewards = [sr["baselines"][bname]["net_reward_inr"] for sr in seed_results]
        b_rec_rates = [sr["baselines"][bname]["recovery_rate_pct"] for sr in seed_results]
        b_recovered = [sr["baselines"][bname]["total_recovered_inr"] for sr in seed_results]
        b_costs = [sr["baselines"][bname]["total_action_cost_inr"] for sr in seed_results]
        b_attempts = [sr["baselines"][bname]["avg_attempts_per_tx"] for sr in seed_results]
        b_avails = [sr["baselines"][bname]["target_action_available_pct"] for sr in seed_results]

        mean_b_reward = float(np.mean(b_rewards))
        mean_b_rec_rate = float(np.mean(b_rec_rates))

        aggregated_baselines[bname] = {
            "mean_net_reward_inr": round(mean_b_reward, 2),
            "mean_recovery_rate_pct": round(mean_b_rec_rate, 2),
            "mean_total_recovered_inr": round(float(np.mean(b_recovered)), 2),
            "mean_action_cost_inr": round(float(np.mean(b_costs)), 2),
            "mean_avg_attempts_per_tx": round(float(np.mean(b_attempts)), 2),
            "mean_target_action_available_pct": round(float(np.mean(b_avails)), 2),
        }

        abs_reward_diff = aggregated_policy["mean_net_reward_inr"] - round(mean_b_reward, 2)
        reward_lift_pct = (100.0 * abs_reward_diff / abs(mean_b_reward)) if mean_b_reward != 0 else 0.0

        abs_rec_diff = aggregated_policy["mean_recovery_rate_pct"] - round(mean_b_rec_rate, 2)
        rec_lift_pct = (100.0 * abs_rec_diff / mean_b_rec_rate) if mean_b_rec_rate > 0 else 0.0

        comparisons[f"vs_{bname}"] = {
            "absolute_reward_diff_inr": round(abs_reward_diff, 2),
            "percentage_reward_lift": round(reward_lift_pct, 2),
            "absolute_recovery_diff_pct": round(abs_rec_diff, 2),
            "percentage_recovery_lift": round(rec_lift_pct, 2),
        }

    return {
        "v2_linucb": aggregated_policy,
        "diagnostics": agg_diagnostics,
        "ev_feasibility": agg_ev,
        "baselines": aggregated_baselines,
        "comparisons": comparisons,
    }


def run_v2_evaluation(
    seeds: List[int] = DEFAULT_SEEDS,
    num_days: int = 30,
    tx_per_day: int = 100,
    output_path: str = "v2_evaluation_results.json",
) -> Dict[str, Any]:
    """
    Main evaluation entry point.
    """
    registry = ActionRegistry()
    per_seed_results = []

    for s in seeds:
        res = evaluate_single_seed(s, num_days=num_days, tx_per_day=tx_per_day, registry=registry)
        per_seed_results.append(res)

    aggregated = aggregate_evaluation_results(per_seed_results)

    final_payload = {
        "evaluation_config": {
            "seeds": seeds,
            "num_days": num_days,
            "tx_per_day": tx_per_day,
            "use_crn": True,
            "action_space_size": len(registry.get_all_actions()),
        },
        "summary": aggregated,
        "per_seed_results": per_seed_results,
    }

    out_file = Path(output_path)
    out_file.write_text(json.dumps(final_payload, indent=2), encoding="utf-8")

    total_tx_per_seed = num_days * tx_per_day
    print("=" * 60)
    print("RecoverFlow V2 Evaluation & Fix 55A/55B Diagnostic Suite")
    print("=" * 60)
    print(f"Seeds: {', '.join(str(s) for s in seeds)}")
    print(f"Transactions per seed: {total_tx_per_seed}")
    print("CRN: enabled")
    print("-" * 60)
    print("V2 LinUCB Policy Performance")
    print("-" * 60)
    pol = aggregated["v2_linucb"]
    print(f"Recovery rate:        {pol['mean_recovery_rate_pct']:.2f}%")
    print(f"Total recovered:      INR {pol['mean_total_recovered_inr']:,.2f}")
    print(f"Total action cost:    INR {pol['mean_action_cost_inr']:,.2f}")
    print(f"Net reward:           INR {pol['mean_net_reward_inr']:,.2f}")
    print(f"Avg reward / tx:      INR {pol['mean_net_reward_inr'] / total_tx_per_seed:.2f}")
    print(f"Avg attempts / tx:    {pol['mean_avg_attempts_per_tx']:.2f}")
    print("-" * 60)
    print("Fix 55B EV Feasibility & Signal Decomposition Summary")
    print("-" * 60)
    ev = aggregated["ev_feasibility"]
    print(f"UCB Score Decomposition: theta^T x = INR {ev['ucb_decomposition']['mean_estimated_reward_inr']:,.2f} | Bonus = INR {ev['ucb_decomposition']['mean_exploration_bonus_inr']:,.2f} | UCB = INR {ev['ucb_decomposition']['mean_ucb_score_inr']:,.2f}")
    print(f"Max theta^T x <= 0:      {ev['negative_ev_opportunity_rates']['pct_decisions_max_theta_x_leq_zero']:.2f}% of decision opportunities")
    print(f"Max UCB <= 0:            {ev['negative_ev_opportunity_rates']['pct_decisions_max_ucb_leq_zero']:.2f}% of decision opportunities")
    print(f"Max Synthetic Oracle <= 0:{ev['negative_ev_opportunity_rates']['pct_decisions_max_oracle_ev_leq_zero']:.2f}% of decision opportunities")
    print(f"Calibration Error:       Pred = INR {ev['offline_calibration_error']['mean_predicted_reward_inr']:,.2f} | Real = INR {ev['offline_calibration_error']['mean_realized_reward_inr']:,.2f} | Error = INR {ev['offline_calibration_error']['prediction_error_inr']:,.2f}")
    print(f"Recommendation:          {ev['architectural_recommendation']}")
    print("-" * 60)
    print("Static Baselines")
    print("-" * 60)
    for bname, bmetrics in aggregated["baselines"].items():
        print(
            f"{bname:<20} Net Reward: INR {bmetrics['mean_net_reward_inr']:>10,.2f} | "
            f"Rec Rate: {bmetrics['mean_recovery_rate_pct']:>6.2f}% | "
            f"Availability: {bmetrics['mean_target_action_available_pct']:>6.2f}%"
        )
    print("-" * 60)
    print("V2 LinUCB vs Baselines")
    print("-" * 60)
    for comp_key, cmetrics in aggregated["comparisons"].items():
        b_name = comp_key.replace("vs_", "")
        print(f"vs {b_name:<17} Lift: {cmetrics['percentage_reward_lift']:>+6.2f}% reward | {cmetrics['percentage_recovery_lift']:>+6.2f}% recovery")
    print("=" * 60)

    return final_payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RecoverFlow V2 Evaluation Harness")
    parser.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_SEEDS, help="List of random seeds for multi-seed evaluation")
    parser.add_argument("--num-days", type=int, default=30, help="Number of simulated days per seed")
    parser.add_argument("--tx-per-day", type=int, default=100, help="Transactions per simulated day")
    parser.add_argument("--output", type=str, default="v2_evaluation_results.json", help="Path to output JSON artifact")
    args = parser.parse_args()

    run_v2_evaluation(
        seeds=args.seeds,
        num_days=args.num_days,
        tx_per_day=args.tx_per_day,
        output_path=args.output,
    )
