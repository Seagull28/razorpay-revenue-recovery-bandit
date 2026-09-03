"""
metrics.py
Quantitative evaluation metrics calculation functions for the Bandit-Optimized Retry Scheduler.
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from bandit_retry_scheduler.simulator.config import DEFAULT_RETRY_COST, DELAY_ARMS
from bandit_retry_scheduler.simulator.ground_truth import calculate_recovery_probability


def compute_performance_by_segment(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes overall, per-failure-code, and per-bank metrics from an audit log:
    - total_tx (unique transactions)
    - recovered_tx
    - recovery_rate (%)
    - gross_revenue (INR)
    - retry_cost (INR)
    - net_revenue (INR)
    """
    overall_tx = set()
    overall_rec = set()
    overall_attempts = 0
    overall_gross = 0.0

    by_code = defaultdict(lambda: {"tx": set(), "rec": set(), "attempts": 0, "gross": 0.0})
    by_bank = defaultdict(lambda: {"tx": set(), "rec": set(), "attempts": 0, "gross": 0.0})

    for r in records:
        tx_id = r["transaction_id"]
        ctx = r["context_vector"]
        code = ctx["failure_code"]
        bank = ctx["bank"]
        outcome = r["actual_outcome"]
        amount = r["amount_recovered"]

        overall_tx.add(tx_id)
        overall_attempts += 1

        by_code[code]["tx"].add(tx_id)
        by_code[code]["attempts"] += 1

        by_bank[bank]["tx"].add(tx_id)
        by_bank[bank]["attempts"] += 1

        if outcome == 1:
            overall_rec.add(tx_id)
            overall_gross += amount
            by_code[code]["rec"].add(tx_id)
            by_code[code]["gross"] += amount
            by_bank[bank]["rec"].add(tx_id)
            by_bank[bank]["gross"] += amount

    def build_summary(tx_set, rec_set, attempts, gross):
        n_tx = len(tx_set)
        n_rec = len(rec_set)
        rec_rate = (n_rec / n_tx * 100.0) if n_tx > 0 else 0.0
        cost = attempts * DEFAULT_RETRY_COST
        net = gross - cost
        return {
            "total_tx": n_tx,
            "recovered_tx": n_rec,
            "recovery_rate_pct": rec_rate,
            "gross_revenue": gross,
            "retry_cost": cost,
            "net_revenue": net,
            "total_attempts": attempts,
        }

    res = {
        "overall": build_summary(overall_tx, overall_rec, overall_attempts, overall_gross),
        "by_failure_code": {},
        "by_bank": {},
    }

    for code, d in sorted(by_code.items()):
        res["by_failure_code"][code] = build_summary(d["tx"], d["rec"], d["attempts"], d["gross"])

    for bank, d in sorted(by_bank.items()):
        res["by_bank"][bank] = build_summary(d["tx"], d["rec"], d["attempts"], d["gross"])

    return res


def compute_comparative_lift(base_res: Dict[str, Any], bandit_res: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes absolute and percentage lifts between Baseline and LinUCB metrics.
    """
    def calc_lift(b_summary, l_summary):
        b_rec_rate = b_summary["recovery_rate_pct"]
        l_rec_rate = l_summary["recovery_rate_pct"]
        rec_rate_lift_abs = l_rec_rate - b_rec_rate

        b_net = b_summary["net_revenue"]
        l_net = l_summary["net_revenue"]
        net_lift_abs = l_net - b_net
        net_lift_pct = (net_lift_abs / b_net * 100.0) if b_net != 0 else 0.0

        b_cost = b_summary["retry_cost"]
        l_cost = l_summary["retry_cost"]
        cost_savings_abs = b_cost - l_cost

        return {
            "baseline_recovery_rate_pct": b_rec_rate,
            "linucb_recovery_rate_pct": l_rec_rate,
            "recovery_rate_lift_abs": rec_rate_lift_abs,
            "baseline_net_revenue": b_net,
            "linucb_net_revenue": l_net,
            "net_revenue_lift_abs": net_lift_abs,
            "net_revenue_lift_pct": net_lift_pct,
            "baseline_retry_cost": b_cost,
            "linucb_retry_cost": l_cost,
            "cost_savings_abs": cost_savings_abs,
            "baseline_gross": b_summary["gross_revenue"],
            "linucb_gross": l_summary["gross_revenue"],
        }

    lift_dict = {
        "overall": calc_lift(base_res["overall"], bandit_res["overall"]),
        "by_failure_code": {},
        "by_bank": {},
    }

    for code in base_res["by_failure_code"]:
        if code in bandit_res["by_failure_code"]:
            lift_dict["by_failure_code"][code] = calc_lift(
                base_res["by_failure_code"][code],
                bandit_res["by_failure_code"][code]
            )

    for bank in base_res["by_bank"]:
        if bank in bandit_res["by_bank"]:
            lift_dict["by_bank"][bank] = calc_lift(
                base_res["by_bank"][bank],
                bandit_res["by_bank"][bank]
            )

    return lift_dict


def compute_oracle_regret(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculates the true ground-truth oracle optimal expected reward for each retry attempt
    and compares against LinUCB's expected and realized rewards to compute regret.

    For a context x_t at attempt k:
    - E[R(a)] = p_true(x_t, a) * amount_t - 10.0
    - E[R(stop)] = 0.0 (for attempt k >= 2)
    - Oracle optimal expected reward E[R*_t] = max(E[R(stop)], max_a E[R(a)])
    """
    oracle_expected_rewards = []
    linucb_expected_rewards = []
    linucb_realized_rewards = []
    instantaneous_expected_regret = []

    for r in records:
        ctx = r["context_vector"]
        arm_chosen = r["arm_chosen"]
        realized_reward = r["reward"]
        amount = ctx.get("amount", 1500.0)
        attempt = ctx.get("retry_attempt_number", 1)

        # Ground truth probabilities per arm
        arm_evs = {}
        for arm in DELAY_ARMS:
            p_true = calculate_recovery_probability(ctx, arm)
            ev = p_true * amount - DEFAULT_RETRY_COST
            arm_evs[arm] = ev

        max_arm_ev = max(arm_evs.values())
        if attempt >= 2:
            oracle_ev = max(0.0, max_arm_ev)
        else:
            oracle_ev = max_arm_ev

        p_chosen = calculate_recovery_probability(ctx, arm_chosen)
        chosen_ev = p_chosen * amount - DEFAULT_RETRY_COST

        oracle_expected_rewards.append(oracle_ev)
        linucb_expected_rewards.append(chosen_ev)
        linucb_realized_rewards.append(realized_reward)
        instantaneous_expected_regret.append(oracle_ev - chosen_ev)

    oracle_cum_exp = np.cumsum(oracle_expected_rewards)
    linucb_cum_exp = np.cumsum(linucb_expected_rewards)
    linucb_cum_realized = np.cumsum(linucb_realized_rewards)

    cum_regret_empirical = oracle_cum_exp - linucb_cum_realized
    cum_regret_expected = np.cumsum(instantaneous_expected_regret)

    return {
        "oracle_expected_rewards": np.array(oracle_expected_rewards),
        "linucb_expected_rewards": np.array(linucb_expected_rewards),
        "linucb_realized_rewards": np.array(linucb_realized_rewards),
        "cum_regret_empirical": cum_regret_empirical,
        "cum_regret_expected": cum_regret_expected,
        "final_cum_regret_empirical": float(cum_regret_empirical[-1]) if len(cum_regret_empirical) > 0 else 0.0,
        "final_cum_regret_expected": float(cum_regret_expected[-1]) if len(cum_regret_expected) > 0 else 0.0,
        "total_decisions": len(records),
        "avg_regret_per_decision": float(cum_regret_expected[-1] / len(records)) if len(records) > 0 else 0.0,
    }


def compute_arm_selection_share(
    records: List[Dict[str, Any]],
    failure_code: str,
    bank: str,
    window_size: int = 40,
) -> Dict[str, Any]:
    """
    Computes rolling arm selection shares over time for a specific (failure_code, bank) context pair.
    """
    filtered = [
        r for r in records
        if r["context_vector"]["failure_code"] == failure_code and r["context_vector"]["bank"] == bank
    ]

    if not filtered:
        return {"x": [], "shares": {arm: [] for arm in DELAY_ARMS}, "sample_count": 0}

    n = len(filtered)
    x_indices = []
    shares = {arm: [] for arm in DELAY_ARMS}

    for i in range(n):
        start_idx = max(0, i - window_size + 1)
        window = filtered[start_idx: i + 1]
        w_size = len(window)
        x_indices.append(i + 1)

        counts = defaultdict(int)
        for r in window:
            counts[r["arm_chosen"]] += 1

        for arm in DELAY_ARMS:
            shares[arm].append((counts[arm] / w_size) * 100.0)

    return {
        "x": x_indices,
        "shares": shares,
        "sample_count": n,
        "failure_code": failure_code,
        "bank": bank,
    }


def compute_cold_start_metrics(
    records: List[Dict[str, Any]],
    n_tx: int = 100,
    failure_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Quantifies policy performance during cold start (first n_tx transactions)
    versus mature stage (last n_tx transactions).
    Optionally filters by a specific failure_code (e.g. 'issuer_timeout').
    """
    if failure_code:
        filtered_records = [r for r in records if r["context_vector"].get("failure_code") == failure_code]
    else:
        filtered_records = records

    # Group records by transaction order
    tx_order = []
    seen = set()
    for r in filtered_records:
        tx_id = r["transaction_id"]
        if tx_id not in seen:
            seen.add(tx_id)
            tx_order.append(tx_id)

    first_tx_ids = set(tx_order[:n_tx])
    last_tx_ids = set(tx_order[-n_tx:])

    def summarize_slice(tx_subset):
        slice_records = [r for r in filtered_records if r["transaction_id"] in tx_subset]
        rec_ids = {r["transaction_id"] for r in slice_records if r["actual_outcome"] == 1}
        attempts = len(slice_records)
        gross = sum(r["amount_recovered"] for r in slice_records if r["actual_outcome"] == 1)
        cost = attempts * DEFAULT_RETRY_COST
        net = gross - cost
        total_tx = len(tx_subset)
        return {
            "total_tx": total_tx,
            "recovered_tx": len(rec_ids),
            "recovery_rate_pct": (len(rec_ids) / total_tx * 100.0) if total_tx > 0 else 0.0,
            "gross_revenue": gross,
            "retry_cost": cost,
            "net_revenue": net,
            "total_attempts": attempts,
            "avg_net_per_tx": (net / total_tx) if total_tx > 0 else 0.0,
        }

    return {
        "first_n": summarize_slice(first_tx_ids),
        "last_n": summarize_slice(last_tx_ids),
        "n_tx": n_tx,
        "failure_code": failure_code,
    }


def compute_drift_adaptation_metrics(
    records: List[Dict[str, Any]],
    bank: str = "Bank D",
    failure_code: str = "do_not_honor",
    window_size: int = 15,
) -> Dict[str, Any]:
    """
    Analyzes Bank D's do_not_honor transactions across simulated days to quantify drift adaptation.
    """
    filtered = [
        r for r in records
        if r["context_vector"]["bank"] == bank and r["context_vector"]["failure_code"] == failure_code
    ]

    filtered.sort(key=lambda r: (r["context_vector"].get("simulated_day", 1), r["timestamp"]))

    days = []
    outcomes = []
    arms = []
    tx_ids = []

    for r in filtered:
        days.append(r["context_vector"].get("simulated_day", 1))
        outcomes.append(r["actual_outcome"])
        arms.append(r["arm_chosen"])
        tx_ids.append(r["transaction_id"])

    # Compute pre-drift (day < 20) vs post-drift (day >= 20) summary
    pre_drift_records = [r for r in filtered if r["context_vector"].get("simulated_day", 1) < 20]
    post_drift_records = [r for r in filtered if r["context_vector"].get("simulated_day", 1) >= 20]

    def summarize_drift_slice(recs):
        n_attempts = len(recs)
        tx_ids = {r["transaction_id"] for r in recs}
        rec_ids = {r["transaction_id"] for r in recs if r["actual_outcome"] == 1}
        gross = sum(r["amount_recovered"] for r in recs if r["actual_outcome"] == 1)
        cost = n_attempts * DEFAULT_RETRY_COST
        n_tx = len(tx_ids)
        return {
            "total_tx": n_tx,
            "recovered_tx": len(rec_ids),
            "recovery_rate_pct": (len(rec_ids) / n_tx * 100.0) if n_tx > 0 else 0.0,
            "gross_revenue": gross,
            "retry_cost": cost,
            "net_revenue": gross - cost,
            "total_attempts": n_attempts,
            "arm_distribution": {arm: sum(1 for r in recs if r["arm_chosen"] == arm) for arm in DELAY_ARMS},
        }

    # Rolling recovery rate by transaction index
    rolling_recovery = []
    n = len(filtered)
    for i in range(n):
        start_idx = max(0, i - window_size + 1)
        win_records = filtered[start_idx: i + 1]
        win_rec_ids = {r["transaction_id"] for r in win_records if r["actual_outcome"] == 1}
        win_tx_ids = {r["transaction_id"] for r in win_records}
        rolling_recovery.append((len(win_rec_ids) / len(win_tx_ids) * 100.0) if win_tx_ids else 0.0)

    return {
        "pre_drift": summarize_drift_slice(pre_drift_records),
        "post_drift": summarize_drift_slice(post_drift_records),
        "simulated_days": days,
        "rolling_recovery": rolling_recovery,
        "arms": arms,
        "sample_count": n,
    }


def analyze_policy_audit(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Analyzes an audit record list to group metrics by failure code.
    Returns dictionary mapping failure code to total_tx, recovered_tx, rec_rate_pct, gross_revenue, retry_cost, net_revenue, attempts.
    """
    by_code = defaultdict(lambda: {
        "gross_revenue": 0.0,
        "retry_cost": 0.0,
        "attempts": 0,
        "tx_ids": set(),
        "recovered_ids": set(),
    })
    for r in records:
        ctx = r["context_vector"] if isinstance(r, dict) else r.context_vector
        code = ctx["failure_code"]
        tx_id = r["transaction_id"] if isinstance(r, dict) else r.transaction_id
        actual_outcome = r["actual_outcome"] if isinstance(r, dict) else r.actual_outcome
        amount_recovered = r["amount_recovered"] if isinstance(r, dict) else r.amount_recovered

        by_code[code]["tx_ids"].add(tx_id)
        by_code[code]["attempts"] += 1
        by_code[code]["retry_cost"] += 10.0
        if actual_outcome == 1:
            by_code[code]["recovered_ids"].add(tx_id)
            by_code[code]["gross_revenue"] += amount_recovered

    res = {}
    for code, d in by_code.items():
        res[code] = {
            "total_tx": len(d["tx_ids"]),
            "recovered_tx": len(d["recovered_ids"]),
            "rec_rate_pct": len(d["recovered_ids"]) / len(d["tx_ids"]) * 100.0 if d["tx_ids"] else 0.0,
            "gross_revenue": d["gross_revenue"],
            "retry_cost": d["retry_cost"],
            "net_revenue": d["gross_revenue"] - d["retry_cost"],
            "attempts": d["attempts"],
        }
    return res

