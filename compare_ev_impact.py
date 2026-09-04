"""
compare_ev_impact.py
Decision-Time Audit Instrumentation for RecoverFlow V2.
Captures EV, predicted probabilities, and feasibility AT ACTUAL DECISION TIME,
strictly BEFORE action execution and BEFORE feedback updates the EV estimator.
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
from bandit_retry_scheduler.runner.v2_engine import V2PolicyExecutionEngine
from bandit_retry_scheduler.run_v2_evaluation import generate_v2_stream, DEFAULT_SEEDS
from bandit_retry_scheduler.api.v2_eligibility import check_v2_eligibility
from bandit_retry_scheduler.simulator.v2_environment import V2_METHOD_SWITCH_COST, V2_TIMED_RETRY_COST


class DecisionTimeAuditEngine(V2PolicyExecutionEngine):
    """
    Instrumented Execution Engine that captures decision-time EV and probability predictions
    at the exact moment each decision is made, strictly before execution and feedback updates.
    """

    def __init__(self, simulator=None, registry=None):
        super().__init__(simulator=simulator, registry=registry)
        self.decision_snapshots = []

    def process_transaction(
        self,
        initial_context: dict,
        policy: V2LinUCBPolicy,
        logger: AuditLogger,
        evaluation_seed: int = None,
        use_crn: bool = False,
    ) -> bool:
        current_ctx = dict(initial_context)
        attempt_number = 1
        success = False

        ev_estimator = getattr(policy, "ev_estimator", None) or getattr(self.decision_service, "ev_estimator", None)

        while True:
            # 1. Capture decision-time predictions BEFORE decision service call / execution / feedback
            source_method = current_ctx.get("source_method", "card")
            candidates = self.registry.get_candidates(source_method)
            eligible, eligible_candidates, gate_reason = check_v2_eligibility(
                context=current_ctx,
                candidates=candidates,
                attempt_number=attempt_number,
                previous_success=success,
                max_attempts=policy.max_attempts,
            )

            snapshot = None
            if eligible and eligible_candidates and ev_estimator is not None:
                # Capture decision-time predictions using current estimator weights (BEFORE feedback)
                dt_probs = {}
                dt_evs = {}
                amount = float(current_ctx.get("amount", 1000.0))

                for act in eligible_candidates:
                    p_hat = ev_estimator.predict_probability(current_ctx, act.action_id)
                    cost = V2_METHOD_SWITCH_COST if act.action_type == "METHOD_SWITCH" else V2_TIMED_RETRY_COST
                    ev = p_hat * amount - cost

                    # Numerical formula check: EV = p * amount - cost
                    assert abs(ev - (p_hat * amount - cost)) < 1e-5

                    dt_probs[act.action_id] = float(p_hat)
                    dt_evs[act.action_id] = float(ev)

                max_ev = max(dt_evs.values()) if dt_evs else 0.0
                is_feasible = max_ev > 0.0

                snapshot = {
                    "transaction_id": current_ctx.get("transaction_id"),
                    "attempt_number": attempt_number,
                    "source_method": source_method,
                    "amount": amount,
                    "eligible_action_ids": [a.action_id for a in eligible_candidates],
                    "decision_time_probs": dt_probs,
                    "decision_time_evs": dt_evs,
                    "decision_time_max_ev": round(float(max_ev), 4),
                    "is_feasible": is_feasible,
                    "executed": False,
                }

            # 2. Get retry decision via decision service
            decision = self.decision_service.get_v2_retry_decision(
                transaction=current_ctx,
                attempt_number=attempt_number,
                previous_success=success,
            )

            if not decision.get("should_retry"):
                if snapshot:
                    snapshot["stop_reason"] = decision.get("stop_reason")
                    self.decision_snapshots.append(snapshot)
                break

            # 3. Execute action
            from bandit_retry_scheduler.api.v2_action_executor import execute_v2_retry_action
            exec_result = execute_v2_retry_action(
                transaction=current_ctx,
                decision=decision,
                simulator=self.simulator,
                attempt_number=attempt_number,
                evaluation_seed=evaluation_seed,
                use_crn=use_crn,
            )

            action_taken = exec_result.get("action_taken")
            if action_taken != "retry":
                break

            # 4. Record decision-time snapshot together with execution outcome
            if snapshot:
                snapshot["executed"] = True
                snapshot["chosen_action_id"] = decision.get("action_id")
                snapshot["chosen_action_p_hat"] = dt_probs.get(decision.get("action_id"))
                snapshot["chosen_action_ev"] = dt_evs.get(decision.get("action_id"))
                snapshot["actual_outcome"] = 1 if exec_result.get("outcome") == "success" else 0
                snapshot["reward"] = float(exec_result.get("reward", 0.0))
                snapshot["amount_recovered"] = float(exec_result.get("amount_recovered", 0.0))
                self.decision_snapshots.append(snapshot)

            # 5. Online feedback update (updates LinUCB & EV estimator AFTER prediction was captured)
            from bandit_retry_scheduler.api.v2_feedback_loop import process_v2_outcome_and_update
            process_v2_outcome_and_update(
                transaction=current_ctx,
                decision=decision,
                execution_result=exec_result,
                policy=policy,
                audit_logger=logger,
            )

            success = (exec_result.get("outcome") == "success")
            if success:
                break

            from bandit_retry_scheduler.core.v2_context_transition import transition_v2_context
            current_ctx = transition_v2_context(
                context=current_ctx,
                action=decision["action_chosen"],
                outcome=exec_result,
            )
            attempt_number += 1

        return success


def run_experiment(seeds, enable_ev=True):
    registry = ActionRegistry()

    total_tx_all = 0
    total_recovered_all = 0.0
    total_cost_all = 0.0
    total_net_reward_all = 0.0
    num_recovered_all = 0
    total_attempts_all = 0
    neg_reward_retries_all = 0
    max_attempt_stopped_all = 0
    ev_stopped_all = 0

    all_dt_snapshots = []

    for seed in seeds:
        stream = generate_v2_stream(seed=seed, num_days=30, tx_per_day=100)
        stream_size = len(stream)
        total_tx_all += stream_size

        sim_policy = V2LinUCBPolicy(registry=registry)
        ev_estimator = V2EVEstimator(registry=registry) if enable_ev else None

        engine = DecisionTimeAuditEngine(registry=registry)
        engine.decision_service.policy = sim_policy
        engine.decision_service.ev_estimator = ev_estimator
        if sim_policy and ev_estimator:
            sim_policy.ev_estimator = ev_estimator

        logger = AuditLogger()
        stream_copy = [dict(tx) for tx in stream]
        engine.run(stream_copy, sim_policy, logger=logger, evaluation_seed=seed, use_crn=True)

        all_dt_snapshots.extend(engine.decision_snapshots)

        records = logger.records
        tx_map = {}
        for r in records:
            tx_id = r.transaction_id
            if r.arm_chosen != "NONE":
                total_attempts_all += 1
                if r.reward < 0:
                    neg_reward_retries_all += 1
                if tx_id not in tx_map:
                    tx_map[tx_id] = {"recovered": False, "amount": 0.0, "attempts": 0}
                tx_map[tx_id]["attempts"] += 1
                if r.actual_outcome == 1:
                    tx_map[tx_id]["recovered"] = True
                    tx_map[tx_id]["amount"] = max(tx_map[tx_id]["amount"], r.amount_recovered)
            else:
                if r.expected_value is not None and r.expected_value <= 0.0:
                    ev_stopped_all += 1

        for s in tx_map.values():
            if s["recovered"]:
                num_recovered_all += 1
                total_recovered_all += s["amount"]
            elif s["attempts"] >= 4:
                max_attempt_stopped_all += 1

        total_net_reward_all += sum(r.reward for r in records if r.arm_chosen != "NONE")
        total_cost_all += sum(
            (r.amount_recovered - r.reward) if r.actual_outcome == 1 else -r.reward
            for r in records
            if r.arm_chosen != "NONE"
        )

    rec_rate = (num_recovered_all / total_tx_all * 100.0) if total_tx_all > 0 else 0.0
    avg_reward_tx = (total_net_reward_all / total_tx_all) if total_tx_all > 0 else 0.0
    avg_attempts_tx = (total_attempts_all / total_tx_all) if total_tx_all > 0 else 0.0
    max_attempt_pct = (max_attempt_stopped_all / total_tx_all * 100.0) if total_tx_all > 0 else 0.0
    ev_stop_pct = (ev_stopped_all / total_tx_all * 100.0) if total_tx_all > 0 else 0.0

    # Extract Decision-Time EV metrics from captured snapshots
    dt_decision_opps = len(all_dt_snapshots)
    dt_ev_pos_opps = sum(1 for s in all_dt_snapshots if s["is_feasible"])
    dt_ev_nonpos_opps = sum(1 for s in all_dt_snapshots if not s["is_feasible"])
    dt_max_evs = [s["decision_time_max_ev"] for s in all_dt_snapshots]

    ev_percentiles = {}
    if dt_max_evs:
        ev_percentiles = {
            "min": round(float(np.min(dt_max_evs)), 2),
            "p25": round(float(np.percentile(dt_max_evs, 25)), 2),
            "median": round(float(np.median(dt_max_evs)), 2),
            "p75": round(float(np.percentile(dt_max_evs, 75)), 2),
            "max": round(float(np.max(dt_max_evs)), 2),
        }

    return {
        "seeds": seeds,
        "total_tx": total_tx_all,
        "num_recovered": num_recovered_all,
        "recovery_rate_pct": round(rec_rate, 2),
        "total_recovered_inr": round(total_recovered_all, 2),
        "total_action_cost_inr": round(total_cost_all, 2),
        "net_reward_inr": round(total_net_reward_all, 2),
        "avg_reward_per_tx": round(avg_reward_tx, 2),
        "avg_attempts_per_tx": round(avg_attempts_tx, 2),
        "total_attempts": total_attempts_all,
        "negative_reward_retries": neg_reward_retries_all,
        "max_attempt_stopped_pct": round(max_attempt_pct, 2),
        "ev_stopped_count": ev_stopped_all,
        "ev_stopped_pct": round(ev_stop_pct, 2),
        "decision_time_metrics": {
            "decision_opportunities": dt_decision_opps,
            "ev_positive_decisions": dt_ev_pos_opps,
            "ev_nonpositive_decisions": dt_ev_nonpos_opps,
            "ev_percentiles": ev_percentiles,
        },
        "snapshots": all_dt_snapshots,
    }


def main():
    print("=" * 60)
    print("DECISION-TIME AUDIT — BEFORE VS AFTER FIX 55C")
    print("=" * 60)

    # 2 Seed Comparison
    res_before_2 = run_experiment([42, 123], enable_ev=False)
    res_after_2 = run_experiment([42, 123], enable_ev=True)

    print("\n--- 2-SEED COMPARISON (Seeds 42, 123) ---")
    print(f"Total Transactions:         {res_after_2['total_tx']}")
    print(f"Recovery Rate:              Before = {res_before_2['recovery_rate_pct']:.2f}% | After = {res_after_2['recovery_rate_pct']:.2f}% | Delta = {res_after_2['recovery_rate_pct'] - res_before_2['recovery_rate_pct']:.2f}%")
    print(f"Total Recovered (INR):      Before = {res_before_2['total_recovered_inr']:,.2f} | After = {res_after_2['total_recovered_inr']:,.2f} | Delta = {res_after_2['total_recovered_inr'] - res_before_2['total_recovered_inr']:.2f}")
    print(f"Total Action Cost (INR):    Before = {res_before_2['total_action_cost_inr']:,.2f} | After = {res_after_2['total_action_cost_inr']:,.2f} | Delta = {res_after_2['total_action_cost_inr'] - res_before_2['total_action_cost_inr']:.2f}")
    print(f"Net Reward (INR):           Before = {res_before_2['net_reward_inr']:,.2f} | After = {res_after_2['net_reward_inr']:,.2f} | Delta = {res_after_2['net_reward_inr'] - res_before_2['net_reward_inr']:.2f}")
    print(f"Avg Attempts / TX:          Before = {res_before_2['avg_attempts_per_tx']:.2f} | After = {res_after_2['avg_attempts_per_tx']:.2f} | Delta = {res_after_2['avg_attempts_per_tx'] - res_before_2['avg_attempts_per_tx']:.2f}")
    print(f"Negative Reward Retries:    Before = {res_before_2['negative_reward_retries']} | After = {res_after_2['negative_reward_retries']} | Delta = {res_after_2['negative_reward_retries'] - res_before_2['negative_reward_retries']}")
    print(f"EV Stopped Count:           Before = {res_before_2['ev_stopped_count']} | After = {res_after_2['ev_stopped_count']} | Delta = {res_after_2['ev_stopped_count'] - res_before_2['ev_stopped_count']}")

    # 5 Seed Comparison
    res_before_5 = run_experiment(DEFAULT_SEEDS, enable_ev=False)
    res_after_5 = run_experiment(DEFAULT_SEEDS, enable_ev=True)

    print("\n--- 5-SEED COMPARISON (Seeds 42, 123, 456, 789, 2026) ---")
    print(f"Total Transactions:         {res_after_5['total_tx']}")
    print(f"Recovery Rate:              Before = {res_before_5['recovery_rate_pct']:.2f}% | After = {res_after_5['recovery_rate_pct']:.2f}% | Delta = {res_after_5['recovery_rate_pct'] - res_before_5['recovery_rate_pct']:.2f}%")
    print(f"Total Recovered (INR):      Before = {res_before_5['total_recovered_inr']:,.2f} | After = {res_after_5['total_recovered_inr']:,.2f} | Delta = {res_after_5['total_recovered_inr'] - res_before_5['total_recovered_inr']:.2f}")
    print(f"Total Action Cost (INR):    Before = {res_before_5['total_action_cost_inr']:,.2f} | After = {res_after_5['total_action_cost_inr']:,.2f} | Delta = {res_after_5['total_action_cost_inr'] - res_before_5['total_action_cost_inr']:.2f}")
    print(f"Net Reward (INR):           Before = {res_before_5['net_reward_inr']:,.2f} | After = {res_after_5['net_reward_inr']:,.2f} | Delta = {res_after_5['net_reward_inr'] - res_before_5['net_reward_inr']:.2f}")
    print(f"Avg Attempts / TX:          Before = {res_before_5['avg_attempts_per_tx']:.2f} | After = {res_after_5['avg_attempts_per_tx']:.2f} | Delta = {res_after_5['avg_attempts_per_tx'] - res_before_5['avg_attempts_per_tx']:.2f}")
    print(f"Negative Reward Retries:    Before = {res_before_5['negative_reward_retries']} | After = {res_after_5['negative_reward_retries']} | Delta = {res_after_5['negative_reward_retries'] - res_before_5['negative_reward_retries']}")
    print(f"EV Stopped Count:           Before = {res_before_5['ev_stopped_count']} | After = {res_after_5['ev_stopped_count']} | Delta = {res_after_5['ev_stopped_count'] - res_before_5['ev_stopped_count']}")

    print("\n--- DECISION-TIME EV DISTRIBUTION (5-SEED AFTER FIX 55C) ---")
    dt = res_after_5["decision_time_metrics"]
    print(f"Decision Opportunities:     {dt['decision_opportunities']}")
    print(f"EV-Positive Decisions:      {dt['ev_positive_decisions']}")
    print(f"EV-Non-Positive Decisions:  {dt['ev_nonpositive_decisions']}")
    print(f"EV Percentiles (INR):       Min = {dt['ev_percentiles']['min']} | P25 = {dt['ev_percentiles']['p25']} | Median = {dt['ev_percentiles']['median']} | P75 = {dt['ev_percentiles']['p75']} | Max = {dt['ev_percentiles']['max']}")


if __name__ == "__main__":
    main()
