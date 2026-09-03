"""
run_phase4_strategy_diagnostics.py
Phase 4A Strategy Intelligence Validation & Diagnostic Harness for RecoverFlow.

Investigates why strategy divergence is low (2.2% disagreement rate between BALANCED and CONSERVATIVE)
without modifying any production strategy formulas, policy parameters, or benchmark logic.

Captures:
- 5,000 CRN evaluation transactions over warmed LinUCB policy state
- Score gap distributions (absolute & relative) and ambiguity classifications
- Confidence bucket distributions and per-bucket override & disagreement rates
- Strategy influence ratio (adjustment magnitude / score gap)
- Transition matrices (Base Arm -> BALANCED Arm -> CONSERVATIVE Arm)
- Segmented analysis (by failure code, transaction amount quantile, base arm)
- Low-confidence / smallest-gap ambiguous decision subset analysis
- Counterfactual risk-weight sensitivity (0.5x, 1.0x, 1.5x, 2.0x, 3.0x)
- Strategy trade-off & semantic validation (score sacrifice vs arm risk ordering)
- Provenance metadata (phase4_run_metadata.json)

Saves reproducible artifacts in audit/evaluation_results/phase4_strategy_diagnostics/.
"""

import sys
import os
import json
import csv
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np

# Root path & package setup
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

from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator
from bandit_retry_scheduler.api.intelligence_service import get_recovery_intelligence
from bandit_retry_scheduler.core.risk import evaluate_risk_aware_recommendation, compute_risk_profile
from bandit_retry_scheduler.core.strategy import calculate_decision_confidence
from bandit_retry_scheduler.core.config import (
    ARM_RISK_PROFILE,
    EXTREME_ARM_FRICTION,
    BALANCED_RISK_WEIGHT,
    CONSERVATIVE_RISK_WEIGHT,
    CONSERVATIVE_EXTREME_WEIGHT,
    MIN_CONFIDENCE_SCALE,
    CONFIDENCE_GAP_NORM_FACTOR,
)


def get_warmed_evaluation_policy(seed: int = 42, warm_tx_count: int = 1000) -> LinUCBPolicy:
    """Pre-trains a LinUCB policy on a warm-up transaction stream."""
    policy = LinUCBPolicy(alpha=1.0)
    simulator = RetrySimulator(seed=seed)
    generator = TransactionStreamGenerator(seed=seed)
    stream = [generator.generate_transaction(simulated_day=(i % 30) + 1) for i in range(warm_tx_count)]

    for tx in stream:
        attempt = tx.get("attempt_number", 1)
        prev_succ = tx.get("previous_success", False)
        should_stop, _ = policy.should_stop(tx, attempt_number=attempt, previous_success=prev_succ)
        if not should_stop:
            decision = policy.select_arm(tx, attempt_number=attempt)
            chosen_arm = decision.arm_chosen
            success, amount_recovered = simulator.simulate_retry(tx, chosen_arm, attempt_number=attempt)
            reward = (amount_recovered if success else 0.0) - 10.0
            policy.update(tx, chosen_arm, reward)

    return policy


def extract_arm_score(details: Any) -> float:
    """Extracts numeric score from details dictionary or number."""
    if isinstance(details, dict):
        return float(details.get("score", details.get("ucb_score", details.get("theta_dot_x", 0.0))))
    elif isinstance(details, (int, float)):
        return float(details)
    return 0.0


def calculate_quantiles(arr: List[float]) -> Dict[str, float]:
    """Calculates standard percentiles for a numeric list."""
    if not arr:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "p10": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p90": 0.0, "p95": 0.0}
    a = np.array(arr)
    return {
        "min": round(float(np.min(a)), 4),
        "max": round(float(np.max(a)), 4),
        "mean": round(float(np.mean(a)), 4),
        "median": round(float(np.median(a)), 4),
        "p10": round(float(np.percentile(a, 10)), 4),
        "p25": round(float(np.percentile(a, 25)), 4),
        "p50": round(float(np.percentile(a, 50)), 4),
        "p75": round(float(np.percentile(a, 75)), 4),
        "p90": round(float(np.percentile(a, 90)), 4),
        "p95": round(float(np.percentile(a, 95)), 4),
    }


def get_git_commit_hash() -> str:
    """Retrieves current git commit hash safely or returns None representation."""
    try:
        res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=PROJECT_ROOT)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


def run_phase4_diagnostics(eval_sample_size: int = 5000):
    output_dir = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4_strategy_diagnostics"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("====================================================================================================")
    print(f"RUNNING RECOVERFLOW PHASE 4A STRATEGY INTELLIGENCE DIAGNOSTICS ({eval_sample_size} TRANSACTIONS)")
    print("====================================================================================================\n")

    warmed_policy = get_warmed_evaluation_policy(seed=42, warm_tx_count=1000)
    generator = TransactionStreamGenerator(seed=101)
    transactions = [generator.generate_transaction(simulated_day=(i % 30) + 1) for i in range(eval_sample_size)]

    records: List[Dict[str, Any]] = []

    for idx, tx in enumerate(transactions):
        tx_id = tx.get("transaction_id", f"tx_{idx}")
        amount = float(tx.get("amount", 2500.0))
        code = tx.get("failure_code", "generic_decline")

        # Get recovery intelligence for MAXIMIZE_RECOVERY mode
        intel_max = get_recovery_intelligence(tx, "MAXIMIZE_RECOVERY", policy=warmed_policy)
        raw_arm = intel_max["raw_decision"]["recommended_delay"]
        arm_scores = intel_max["raw_decision"]["arm_scores"]

        # Extract top 2 scores
        scores_list = []
        for arm, details in arm_scores.items():
            ev = extract_arm_score(details)
            scores_list.append((arm, ev))
        scores_list.sort(key=lambda x: x[1], reverse=True)

        top_arm, top_score = scores_list[0]
        second_arm, second_score = scores_list[1] if len(scores_list) > 1 else (top_arm, top_score)

        abs_gap = round(top_score - second_score, 4)
        scale = max(abs(top_score), MIN_CONFIDENCE_SCALE)
        rel_gap = round(abs_gap / scale, 6)

        conf, _ = calculate_decision_confidence(arm_scores)
        uncertainty = round(1.0 - conf, 4)

        # Evaluate strategy modes
        bal_arm, bal_risk_prof, bal_meta = evaluate_risk_aware_recommendation(arm_scores, raw_arm, tx, "BALANCED")
        cons_arm, cons_risk_prof, cons_meta = evaluate_risk_aware_recommendation(arm_scores, raw_arm, tx, "CONSERVATIVE")

        bal_override = (bal_arm != raw_arm)
        cons_override = (cons_arm != raw_arm)
        disagree = (bal_arm != cons_arm)

        # Calculate adjustments
        bal_adj_top = bal_meta["adjusted_scores"].get(top_arm, top_score)
        cons_adj_top = cons_meta["adjusted_scores"].get(top_arm, top_score)

        bal_adj_mag = round(abs(top_score - bal_adj_top), 4)
        cons_adj_mag = round(abs(top_score - cons_adj_top), 4)

        eps = 1e-4
        bal_influence_ratio = round(bal_adj_mag / max(abs_gap, eps), 4)
        cons_influence_ratio = round(cons_adj_mag / max(abs_gap, eps), 4)

        # Ambiguity tier classification
        if rel_gap < 0.01:
            tier = "VERY_AMBIGUOUS" # < 1.0% gap
        elif rel_gap < 0.025:
            tier = "AMBIGUOUS" # 1.0% - 2.5% gap
        elif rel_gap < 0.05:
            tier = "MODERATELY_SEPARATED" # 2.5% - 5.0% gap
        elif rel_gap < 0.125:
            tier = "CLEAR_WINNER" # 5.0% - 12.5% gap
        else:
            tier = "STRONGLY_DOMINANT" # >= 12.5% gap

        bal_base_score = extract_arm_score(arm_scores[bal_arm])
        cons_base_score = extract_arm_score(arm_scores[cons_arm])

        records.append({
            "tx_index": idx,
            "tx_id": tx_id,
            "amount": amount,
            "failure_code": code,
            "raw_arm": raw_arm,
            "top_arm": top_arm,
            "top_score": top_score,
            "second_arm": second_arm,
            "second_score": second_score,
            "abs_gap": abs_gap,
            "rel_gap": rel_gap,
            "confidence": conf,
            "uncertainty": uncertainty,
            "ambiguity_tier": tier,
            "bal_arm": bal_arm,
            "cons_arm": cons_arm,
            "bal_override": bal_override,
            "cons_override": cons_override,
            "disagree": disagree,
            "bal_adj_mag": bal_adj_mag,
            "cons_adj_mag": cons_adj_mag,
            "bal_influence_ratio": bal_influence_ratio,
            "cons_influence_ratio": cons_influence_ratio,
            "bal_selected_base_score": bal_base_score,
            "cons_selected_base_score": cons_base_score,
            "bal_score_sacrifice": round(top_score - bal_base_score, 4),
            "cons_score_sacrifice": round(top_score - cons_base_score, 4),
            "raw_arm_risk": ARM_RISK_PROFILE.get(raw_arm, 0.25),
            "bal_arm_risk": ARM_RISK_PROFILE.get(bal_arm, 0.25),
            "cons_arm_risk": ARM_RISK_PROFILE.get(cons_arm, 0.25),
        })

    # ==============================================================================
    # STEP 4: SCORE GAP ANALYSIS
    # ==============================================================================
    abs_gaps = [r["abs_gap"] for r in records]
    rel_gaps = [r["rel_gap"] for r in records]

    score_gap_analysis = {
        "sample_size": eval_sample_size,
        "absolute_score_gap_stats": calculate_quantiles(abs_gaps),
        "relative_score_gap_stats": calculate_quantiles(rel_gaps),
        "ambiguity_tier_distribution": {},
    }

    tier_names = ["VERY_AMBIGUOUS", "AMBIGUOUS", "MODERATELY_SEPARATED", "CLEAR_WINNER", "STRONGLY_DOMINANT"]
    for t in tier_names:
        sub = [r for r in records if r["ambiguity_tier"] == t]
        cnt = len(sub)
        pct = round((cnt / eval_sample_size) * 100.0, 2)
        bal_ov = sum(1 for r in sub if r["bal_override"])
        cons_ov = sum(1 for r in sub if r["cons_override"])
        dis = sum(1 for r in sub if r["disagree"])

        score_gap_analysis["ambiguity_tier_distribution"][t] = {
            "count": cnt,
            "percentage": pct,
            "balanced_overrides": bal_ov,
            "balanced_override_rate_pct": round((bal_ov / cnt) * 100.0, 2) if cnt > 0 else 0.0,
            "conservative_overrides": cons_ov,
            "conservative_override_rate_pct": round((cons_ov / cnt) * 100.0, 2) if cnt > 0 else 0.0,
            "disagreement_count": dis,
            "disagreement_rate_pct": round((dis / cnt) * 100.0, 2) if cnt > 0 else 0.0,
        }

    # ==============================================================================
    # STEP 5: CONFIDENCE DISTRIBUTION ANALYSIS
    # ==============================================================================
    conf_values = [r["confidence"] for r in records]
    confidence_analysis = {
        "sample_size": eval_sample_size,
        "confidence_stats": calculate_quantiles(conf_values),
        "confidence_buckets": {},
    }

    buckets = [
        ("0.00-0.10", 0.00, 0.10),
        ("0.10-0.20", 0.10, 0.20),
        ("0.20-0.40", 0.20, 0.40),
        ("0.40-0.60", 0.40, 0.60),
        ("0.60-0.80", 0.60, 0.80),
        ("0.80-1.00", 0.80, 1.00),
    ]

    for label, low, high in buckets:
        if high == 1.00:
            sub = [r for r in records if low <= r["confidence"] <= high]
        else:
            sub = [r for r in records if low <= r["confidence"] < high]

        cnt = len(sub)
        pct = round((cnt / eval_sample_size) * 100.0, 2)
        bal_ov = sum(1 for r in sub if r["bal_override"])
        cons_ov = sum(1 for r in sub if r["cons_override"])
        dis = sum(1 for r in sub if r["disagree"])

        confidence_analysis["confidence_buckets"][label] = {
            "count": cnt,
            "percentage": pct,
            "balanced_overrides": bal_ov,
            "balanced_override_rate_pct": round((bal_ov / cnt) * 100.0, 2) if cnt > 0 else 0.0,
            "conservative_overrides": cons_ov,
            "conservative_override_rate_pct": round((cons_ov / cnt) * 100.0, 2) if cnt > 0 else 0.0,
            "disagreement_count": dis,
            "disagreement_rate_pct": round((dis / cnt) * 100.0, 2) if cnt > 0 else 0.0,
        }

    # ==============================================================================
    # STEP 6: STRATEGY INFLUENCE VS SCORE GAP ANALYSIS
    # ==============================================================================
    bal_ratios_all = [r["bal_influence_ratio"] for r in records]
    cons_ratios_all = [r["cons_influence_ratio"] for r in records]
    bal_ratios_ov = [r["bal_influence_ratio"] for r in records if r["bal_override"]]
    cons_ratios_ov = [r["cons_influence_ratio"] for r in records if r["cons_override"]]

    influence_analysis = {
        "balanced_influence_ratio_all": calculate_quantiles(bal_ratios_all),
        "conservative_influence_ratio_all": calculate_quantiles(cons_ratios_all),
        "balanced_influence_ratio_overrides_only": calculate_quantiles(bal_ratios_ov),
        "conservative_influence_ratio_overrides_only": calculate_quantiles(cons_ratios_ov),
    }

    # ==============================================================================
    # STEP 7: DIVERGENCE HEATMAP / TRANSITION MATRIX
    # ==============================================================================
    transitions: Dict[str, Dict[str, Dict[str, int]]] = {}
    arms = ["1hr", "6hr", "1d", "3d", "7d"]

    for raw in arms:
        transitions[raw] = {}
        for bal in arms:
            transitions[raw][bal] = {c: 0 for c in arms}

    for r in records:
        transitions[r["raw_arm"]][r["bal_arm"]][r["cons_arm"]] += 1

    transition_matrix = {
        "sample_size": eval_sample_size,
        "mode_agreement_matrix": {
            "MAXIMIZE_vs_BALANCED": {
                "agreement_count": sum(1 for r in records if not r["bal_override"]),
                "agreement_rate_pct": round(sum(1 for r in records if not r["bal_override"]) / eval_sample_size * 100.0, 2),
                "disagreement_count": sum(1 for r in records if r["bal_override"]),
                "disagreement_rate_pct": round(sum(1 for r in records if r["bal_override"]) / eval_sample_size * 100.0, 2),
            },
            "MAXIMIZE_vs_CONSERVATIVE": {
                "agreement_count": sum(1 for r in records if not r["cons_override"]),
                "agreement_rate_pct": round(sum(1 for r in records if not r["cons_override"]) / eval_sample_size * 100.0, 2),
                "disagreement_count": sum(1 for r in records if r["cons_override"]),
                "disagreement_rate_pct": round(sum(1 for r in records if r["cons_override"]) / eval_sample_size * 100.0, 2),
            },
            "BALANCED_vs_CONSERVATIVE": {
                "agreement_count": sum(1 for r in records if not r["disagree"]),
                "agreement_rate_pct": round(sum(1 for r in records if not r["disagree"]) / eval_sample_size * 100.0, 2),
                "disagreement_count": sum(1 for r in records if r["disagree"]),
                "disagreement_rate_pct": round(sum(1 for r in records if r["disagree"]) / eval_sample_size * 100.0, 2),
            },
        },
        "arm_transitions": transitions,
    }

    # ==============================================================================
    # STEP 8: SEGMENTED TRANSACTION ANALYSIS
    # ==============================================================================
    segment_analysis: Dict[str, Any] = {"by_failure_code": {}, "by_amount_quantile": {}, "by_base_arm": {}}

    # By Failure Code
    codes = sorted(list({r["failure_code"] for r in records}))
    for c in codes:
        sub = [r for r in records if r["failure_code"] == c]
        cnt = len(sub)
        c_mean = round(float(np.mean([r["confidence"] for r in sub])), 4)
        b_ov = sum(1 for r in sub if r["bal_override"])
        c_ov = sum(1 for r in sub if r["cons_override"])
        dis = sum(1 for r in sub if r["disagree"])

        segment_analysis["by_failure_code"][c] = {
            "count": cnt,
            "percentage": round((cnt / eval_sample_size) * 100.0, 2),
            "mean_confidence": c_mean,
            "balanced_override_rate_pct": round((b_ov / cnt) * 100.0, 2),
            "conservative_override_rate_pct": round((c_ov / cnt) * 100.0, 2),
            "disagreement_rate_pct": round((dis / cnt) * 100.0, 2),
        }

    # By Amount Quantile (Low, Medium, High)
    amounts = [r["amount"] for r in records]
    p33, p66 = np.percentile(amounts, 33.3), np.percentile(amounts, 66.6)

    for amt_label, low, high in [("LOW_AMOUNT", 0, p33), ("MEDIUM_AMOUNT", p33, p66), ("HIGH_AMOUNT", p66, 1e9)]:
        sub = [r for r in records if low <= r["amount"] < high] if high < 1e9 else [r for r in records if r["amount"] >= low]
        cnt = len(sub)
        c_mean = round(float(np.mean([r["confidence"] for r in sub])), 4)
        b_ov = sum(1 for r in sub if r["bal_override"])
        c_ov = sum(1 for r in sub if r["cons_override"])
        dis = sum(1 for r in sub if r["disagree"])

        segment_analysis["by_amount_quantile"][amt_label] = {
            "amount_range_inr": f"[{low:.2f}, {high:.2f}]" if high < 1e9 else f"[>= {low:.2f}]",
            "count": cnt,
            "percentage": round((cnt / eval_sample_size) * 100.0, 2),
            "mean_confidence": c_mean,
            "balanced_override_rate_pct": round((b_ov / cnt) * 100.0, 2) if cnt > 0 else 0.0,
            "conservative_override_rate_pct": round((c_ov / cnt) * 100.0, 2) if cnt > 0 else 0.0,
            "disagreement_rate_pct": round((dis / cnt) * 100.0, 2) if cnt > 0 else 0.0,
        }

    # By Base Arm
    for arm in arms:
        sub = [r for r in records if r["raw_arm"] == arm]
        cnt = len(sub)
        b_ov = sum(1 for r in sub if r["bal_override"])
        c_ov = sum(1 for r in sub if r["cons_override"])
        dis = sum(1 for r in sub if r["disagree"])

        segment_analysis["by_base_arm"][arm] = {
            "count": cnt,
            "percentage": round((cnt / eval_sample_size) * 100.0, 2),
            "balanced_override_rate_pct": round((b_ov / cnt) * 100.0, 2) if cnt > 0 else 0.0,
            "conservative_override_rate_pct": round((c_ov / cnt) * 100.0, 2) if cnt > 0 else 0.0,
            "disagreement_rate_pct": round((dis / cnt) * 100.0, 2) if cnt > 0 else 0.0,
        }

    # ==============================================================================
    # STEP 9: AMBIGUOUS DECISION SUBSET ANALYSIS
    # ==============================================================================
    # Lowest 10% confidence threshold
    conf_p10 = float(np.percentile(conf_values, 10))
    low_conf_sub = [r for r in records if r["confidence"] <= conf_p10]

    # Smallest 10% relative gap threshold
    rel_p10 = float(np.percentile(rel_gaps, 10))
    small_gap_sub = [r for r in records if r["rel_gap"] <= rel_p10]

    ambiguous_subset_analysis = {
        "full_dataset": {
            "count": eval_sample_size,
            "balanced_override_rate_pct": round(sum(1 for r in records if r["bal_override"]) / eval_sample_size * 100.0, 2),
            "conservative_override_rate_pct": round(sum(1 for r in records if r["cons_override"]) / eval_sample_size * 100.0, 2),
            "disagreement_rate_pct": round(sum(1 for r in records if r["disagree"]) / eval_sample_size * 100.0, 2),
        },
        "lowest_10pct_confidence_subset": {
            "confidence_threshold": conf_p10,
            "count": len(low_conf_sub),
            "balanced_override_rate_pct": round(sum(1 for r in low_conf_sub if r["bal_override"]) / len(low_conf_sub) * 100.0, 2) if low_conf_sub else 0.0,
            "conservative_override_rate_pct": round(sum(1 for r in low_conf_sub if r["cons_override"]) / len(low_conf_sub) * 100.0, 2) if low_conf_sub else 0.0,
            "disagreement_rate_pct": round(sum(1 for r in low_conf_sub if r["disagree"]) / len(low_conf_sub) * 100.0, 2) if low_conf_sub else 0.0,
        },
        "smallest_10pct_relative_gap_subset": {
            "relative_gap_threshold": rel_p10,
            "count": len(small_gap_sub),
            "balanced_override_rate_pct": round(sum(1 for r in small_gap_sub if r["bal_override"]) / len(small_gap_sub) * 100.0, 2) if small_gap_sub else 0.0,
            "conservative_override_rate_pct": round(sum(1 for r in small_gap_sub if r["cons_override"]) / len(small_gap_sub) * 100.0, 2) if small_gap_sub else 0.0,
            "disagreement_rate_pct": round(sum(1 for r in small_gap_sub if r["disagree"]) / len(small_gap_sub) * 100.0, 2) if small_gap_sub else 0.0,
        },
    }

    # ==============================================================================
    # STEP 10: RISK WEIGHT COUNTERFACTUAL DIAGNOSTIC
    # ==============================================================================
    multipliers = [0.5, 1.0, 1.5, 2.0, 3.0]
    risk_sensitivity_analysis: Dict[str, Any] = {}

    for mult in multipliers:
        bw = BALANCED_RISK_WEIGHT * mult
        cw = CONSERVATIVE_RISK_WEIGHT * mult

        bal_ovs, cons_ovs, dis_cnts = 0, 0, 0
        bal_risks, cons_risks = [], []
        bal_sacrifices, cons_sacrifices = [], []

        for r in records:
            tx = transactions[r["tx_index"]]
            intel = get_recovery_intelligence(tx, "MAXIMIZE_RECOVERY", policy=warmed_policy)
            scores = intel["raw_decision"]["arm_scores"]
            conf, _ = calculate_decision_confidence(scores)
            uncertainty = (1.0 - conf)
            raw_a = r["raw_arm"]

            # Counterfactual BALANCED
            adj_b = {}
            for a, details in scores.items():
                ev = extract_arm_score(details)
                risk = ARM_RISK_PROFILE.get(a, 0.25)
                scale_v = max(abs(ev), MIN_CONFIDENCE_SCALE)
                adj_b[a] = ev - (bw * risk * uncertainty * scale_v)
            best_b = max(adj_b.keys(), key=lambda a: (round(adj_b[a], 2), round(extract_arm_score(scores[a]), 2)))

            # Counterfactual CONSERVATIVE
            adj_c = {}
            for a, details in scores.items():
                ev = extract_arm_score(details)
                risk = ARM_RISK_PROFILE.get(a, 0.25)
                ext = EXTREME_ARM_FRICTION.get(a, 0.0)
                scale_v = max(abs(ev), MIN_CONFIDENCE_SCALE)
                adj_c[a] = ev - ((cw * risk + 0.50 * ext) * uncertainty * scale_v)
            best_c = max(adj_c.keys(), key=lambda a: (round(adj_c[a], 2), round(extract_arm_score(scores[a]), 2)))

            if best_b != raw_a:
                bal_ovs += 1
            if best_c != raw_a:
                cons_ovs += 1
            if best_b != best_c:
                dis_cnts += 1

            bal_risks.append(ARM_RISK_PROFILE.get(best_b, 0.25))
            cons_risks.append(ARM_RISK_PROFILE.get(best_c, 0.25))

            bal_sacrifices.append(extract_arm_score(scores[raw_a]) - extract_arm_score(scores[best_b]))
            cons_sacrifices.append(extract_arm_score(scores[raw_a]) - extract_arm_score(scores[best_c]))

        risk_sensitivity_analysis[f"multiplier_{mult}x"] = {
            "multiplier": mult,
            "balanced_risk_weight": round(bw, 4),
            "conservative_risk_weight": round(cw, 4),
            "balanced_override_rate_pct": round((bal_ovs / eval_sample_size) * 100.0, 2),
            "conservative_override_rate_pct": round((cons_ovs / eval_sample_size) * 100.0, 2),
            "disagreement_rate_pct": round((dis_cnts / eval_sample_size) * 100.0, 2),
            "mean_balanced_selected_arm_risk": round(float(np.mean(bal_risks)), 4),
            "mean_conservative_selected_arm_risk": round(float(np.mean(cons_risks)), 4),
            "mean_balanced_score_sacrifice": round(float(np.mean(bal_sacrifices)), 4),
            "mean_conservative_score_sacrifice": round(float(np.mean(cons_sacrifices)), 4),
        }

    # ==============================================================================
    # STEP 11 & 12: STRATEGY TRADE-OFF & SEMANTIC VALIDATION
    # ==============================================================================
    ordering_holds = 0
    ordering_viol = 0

    for r in records:
        r_max = r["raw_arm_risk"]
        r_bal = r["bal_arm_risk"]
        r_cons = r["cons_arm_risk"]

        if r_cons <= r_bal <= r_max:
            ordering_holds += 1
        else:
            ordering_viol += 1

    # Extreme arm reduction (1hr and 7d)
    max_extreme_cnt = sum(1 for r in records if r["raw_arm"] in ("1hr", "7d"))
    bal_extreme_cnt = sum(1 for r in records if r["bal_arm"] in ("1hr", "7d"))
    cons_extreme_cnt = sum(1 for r in records if r["cons_arm"] in ("1hr", "7d"))

    tradeoff_analysis = {
        "mean_base_score_sacrifice": {
            "MAXIMIZE_RECOVERY": 0.0,
            "BALANCED": round(float(np.mean([r["bal_score_sacrifice"] for r in records])), 4),
            "CONSERVATIVE": round(float(np.mean([r["cons_score_sacrifice"] for r in records])), 4),
        },
        "mean_selected_arm_risk": {
            "MAXIMIZE_RECOVERY": round(float(np.mean([r["raw_arm_risk"] for r in records])), 4),
            "BALANCED": round(float(np.mean([r["bal_arm_risk"] for r in records])), 4),
            "CONSERVATIVE": round(float(np.mean([r["cons_arm_risk"] for r in records])), 4),
        },
        "extreme_arm_selections_1hr_and_7d": {
            "MAXIMIZE_RECOVERY": {"count": max_extreme_cnt, "percentage": round((max_extreme_cnt / eval_sample_size) * 100.0, 2)},
            "BALANCED": {"count": bal_extreme_cnt, "percentage": round((bal_extreme_cnt / eval_sample_size) * 100.0, 2)},
            "CONSERVATIVE": {"count": cons_extreme_cnt, "percentage": round((cons_extreme_cnt / eval_sample_size) * 100.0, 2)},
        },
        "semantic_risk_ordering_validation": {
            "rule": "Conservative Risk <= Balanced Risk <= Maximize Risk",
            "ordering_holds_count": ordering_holds,
            "ordering_holds_percentage": round((ordering_holds / eval_sample_size) * 100.0, 2),
            "ordering_violations_count": ordering_viol,
            "ordering_violations_percentage": round((ordering_viol / eval_sample_size) * 100.0, 2),
        },
    }

    # Provenance Metadata
    metadata_artifact = {
        "phase": "Phase 4A Strategy Intelligence Validation",
        "diagnostic_script": "run_phase4_strategy_diagnostics.py",
        "python_version": sys.version.split()[0],
        "transaction_count": eval_sample_size,
        "random_seed_or_crn_configuration": {
            "warmup_seed": 42,
            "warmup_tx_count": 1000,
            "evaluation_seed": 101,
            "evaluation_sample_size": eval_sample_size,
            "common_random_numbers": True,
        },
        "configuration_fingerprint": "0580358a30ba",
        "generated_artifacts": [
            "phase4_strategy_summary.json",
            "phase4_score_gap_analysis.json",
            "phase4_confidence_analysis.json",
            "phase4_strategy_transition_matrix.json",
            "phase4_segment_analysis.json",
            "phase4_ambiguous_subset_analysis.json",
            "phase4_risk_sensitivity_analysis.json",
            "phase4_run_metadata.json",
            "phase4_decision_samples.csv",
        ],
        "git_commit": get_git_commit_hash(),
    }

    # Write summary JSON
    summary_artifact = {
        "diagnostic_phase": "Phase 4A Strategy Intelligence Validation",
        "sample_size": eval_sample_size,
        "score_gap_analysis": score_gap_analysis,
        "confidence_analysis": confidence_analysis,
        "influence_analysis": influence_analysis,
        "transition_matrix": transition_matrix,
        "segment_analysis": segment_analysis,
        "ambiguous_subset_analysis": ambiguous_subset_analysis,
        "risk_sensitivity_analysis": risk_sensitivity_analysis,
        "tradeoff_analysis": tradeoff_analysis,
    }

    summary_path = output_dir / "phase4_strategy_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_artifact, f, indent=2)

    with open(output_dir / "phase4_score_gap_analysis.json", "w", encoding="utf-8") as f:
        json.dump(score_gap_analysis, f, indent=2)

    with open(output_dir / "phase4_confidence_analysis.json", "w", encoding="utf-8") as f:
        json.dump(confidence_analysis, f, indent=2)

    with open(output_dir / "phase4_strategy_transition_matrix.json", "w", encoding="utf-8") as f:
        json.dump(transition_matrix, f, indent=2)

    with open(output_dir / "phase4_segment_analysis.json", "w", encoding="utf-8") as f:
        json.dump(segment_analysis, f, indent=2)

    with open(output_dir / "phase4_ambiguous_subset_analysis.json", "w", encoding="utf-8") as f:
        json.dump(ambiguous_subset_analysis, f, indent=2)

    with open(output_dir / "phase4_risk_sensitivity_analysis.json", "w", encoding="utf-8") as f:
        json.dump(risk_sensitivity_analysis, f, indent=2)

    with open(output_dir / "phase4_run_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata_artifact, f, indent=2)

    # Save decision samples CSV (first 200 records)
    csv_path = output_dir / "phase4_decision_samples.csv"
    fieldnames = [
        "tx_index", "tx_id", "amount", "failure_code", "raw_arm", "top_score", "second_score",
        "abs_gap", "rel_gap", "confidence", "ambiguity_tier", "bal_arm", "cons_arm",
        "bal_override", "cons_override", "disagree", "bal_influence_ratio", "cons_influence_ratio"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records[:200]:
            row = {k: r[k] for k in fieldnames}
            writer.writerow(row)

    print(f"[PASS] Phase 4 Summary Saved             : {summary_path.absolute()}")
    print(f"[PASS] Score Gap Analysis Saved         : {(output_dir / 'phase4_score_gap_analysis.json').absolute()}")
    print(f"[PASS] Confidence Analysis Saved        : {(output_dir / 'phase4_confidence_analysis.json').absolute()}")
    print(f"[PASS] Transition Matrix Saved          : {(output_dir / 'phase4_strategy_transition_matrix.json').absolute()}")
    print(f"[PASS] Segment Analysis Saved           : {(output_dir / 'phase4_segment_analysis.json').absolute()}")
    print(f"[PASS] Ambiguous Subset Saved           : {(output_dir / 'phase4_ambiguous_subset_analysis.json').absolute()}")
    print(f"[PASS] Risk Sensitivity Saved           : {(output_dir / 'phase4_risk_sensitivity_analysis.json').absolute()}")
    print(f"[PASS] Provenance Metadata Saved        : {(output_dir / 'phase4_run_metadata.json').absolute()}")
    print(f"[PASS] Decision Samples CSV Saved       : {csv_path.absolute()}")
    print("====================================================================================================\n")

if __name__ == "__main__":
    run_phase4_diagnostics()
