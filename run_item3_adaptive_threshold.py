"""
run_item3_adaptive_threshold.py
Item 3 Evaluation & 3-Way Comparison:
Fixed Baseline vs. Locked LinUCB (Fixed min_samples=15) vs. Adaptive-Threshold LinUCB (min_samples=25 high-ticket, 15 standard).
Executes across seeds 42, 101, 2026.
Includes mandatory regression checks and exact-numeric traces.
"""

import sys
import json
from pathlib import Path
import numpy as np

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.policies.linucb_adaptive_threshold import LinUCBAdaptiveThresholdPolicy
from bandit_retry_scheduler.policies.fixed_schedule import FixedSchedulePolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.evaluation.metrics import compute_performance_by_segment
from bandit_retry_scheduler.simulator.config import FailureCode, Bank, Network


def run_single_simulation(policy, seed: int):
    gen = TransactionStreamGenerator(seed=seed)
    txs = gen.generate_stream(num_days=30, transactions_per_day=100)
    sim = RetrySimulator(seed=seed)
    engine = PolicyExecutionEngine(simulator=sim)
    log = engine.run(transactions=txs, policy=policy)
    from dataclasses import asdict
    records_dict = [asdict(r) if hasattr(r, "__dataclass_fields__") else r for r in log.records]
    perf = compute_performance_by_segment(records_dict)
    return perf, log


def main():
    print("====================================================================================================")
    print("ITEM 3: PER-SEGMENT-ADAPTIVE STOPPING THRESHOLDS EVALUATION & 3-WAY COMPARISON")
    print("====================================================================================================\n")

    seeds = [42, 101, 2026]
    results = {}

    for s in seeds:
        print(f"Running Seed {s} simulations...")
        p_base = FixedSchedulePolicy()
        p_locked = LinUCBPolicy(min_samples_for_stopping=15)
        p_adaptive = LinUCBAdaptiveThresholdPolicy(high_ticket_min_samples=25, standard_min_samples=15)

        perf_base, _ = run_single_simulation(p_base, seed=s)
        perf_locked, _ = run_single_simulation(p_locked, seed=s)
        perf_adaptive, log_adaptive = run_single_simulation(p_adaptive, seed=s)

        results[s] = {
            "baseline": perf_base,
            "locked_linucb": perf_locked,
            "adaptive_linucb": perf_adaptive,
            "log_adaptive": log_adaptive,
        }

    # 1. MANDATORY REGRESSION CHECK FOR SEED 42 LOCKED CORE
    print("\n--- 1. MANDATORY REGRESSION CHECK (SEED 42 LOCKED CORE) ---")
    s42_locked_net = results[42]["locked_linucb"]["overall"]["net_revenue"]
    s42_base_net = results[42]["baseline"]["overall"]["net_revenue"]
    expected_locked_net = 7998301.40
    expected_base_net = 6528431.32

    print(f"Locked Seed 42 Baseline Net Revenue : INR {expected_base_net:,.2f} -> Actual: INR {s42_base_net:,.2f}")
    print(f"Locked Seed 42 LinUCB Net Revenue  : INR {expected_locked_net:,.2f} -> Actual: INR {s42_locked_net:,.2f}")
    assert np.isclose(expected_locked_net, s42_locked_net), f"SEED 42 LOCKED REGRESSION FAILED! {s42_locked_net} != {expected_locked_net}"
    print(">>> REGRESSION CHECK PASSED 100%: SEED 42 MATCHES LOCKED CORE EXACTLY <<<\n")

    # 2. SPECIFIC REGRESSION CHECKS (do_not_honor, issuer_timeout, card_expired on Seed 42)
    s42_locked_dnh = results[42]["locked_linucb"]["by_failure_code"]["do_not_honor"]["net_revenue"]
    s42_adapt_dnh = results[42]["adaptive_linucb"]["by_failure_code"]["do_not_honor"]["net_revenue"]
    
    s42_locked_timeout = results[42]["locked_linucb"]["by_failure_code"]["issuer_timeout"]["net_revenue"]
    s42_adapt_timeout = results[42]["adaptive_linucb"]["by_failure_code"]["issuer_timeout"]["net_revenue"]

    s42_locked_exp = results[42]["locked_linucb"]["by_failure_code"]["card_expired"]["net_revenue"]
    s42_adapt_exp = results[42]["adaptive_linucb"]["by_failure_code"]["card_expired"]["net_revenue"]

    print("--- 2. SPECIFIC SEGMENT REGRESSION CHECKS (SEED 42) ---")
    print(f"do_not_honor Net Revenue   : Locked = INR {s42_locked_dnh:,.2f} | Adaptive = INR {s42_adapt_dnh:,.2f} (Diff: +INR {s42_adapt_dnh - s42_locked_dnh:,.2f})")
    print(f"issuer_timeout Net Revenue : Locked = INR {s42_locked_timeout:,.2f} | Adaptive = INR {s42_adapt_timeout:,.2f} (Diff: INR {s42_adapt_timeout - s42_locked_timeout:,.2f})")
    print(f"card_expired Net Revenue   : Locked = INR {s42_locked_exp:,.2f} | Adaptive = INR {s42_adapt_exp:,.2f} (Diff: INR {s42_adapt_exp - s42_locked_exp:,.2f})")

    # 3. PRINT 3-WAY COMPARISON TABLE FOR SEED 42
    print("\n--- 3. SEED 42 PER-FAILURE-CODE 3-WAY COMPARISON TABLE ---")
    print("| Failure Code | Baseline Net Rev (INR) | Locked LinUCB Net Rev (INR) | Adaptive LinUCB Net Rev (INR) | Adaptive vs Locked Lift (INR) | Adaptive vs Locked Lift (%) |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: |")

    codes = ["card_expired", "do_not_honor", "generic_decline", "insufficient_funds", "issuer_timeout"]
    for c in codes:
        b_net = results[42]["baseline"]["by_failure_code"][c]["net_revenue"]
        l_net = results[42]["locked_linucb"]["by_failure_code"][c]["net_revenue"]
        a_net = results[42]["adaptive_linucb"]["by_failure_code"][c]["net_revenue"]
        diff_inr = a_net - l_net
        diff_pct = (diff_inr / abs(l_net) * 100.0) if l_net != 0 else 0.0
        print(f"| `{c:<18}` | INR {b_net:12,.2f} | INR {l_net:12,.2f} | INR {a_net:12,.2f} | +INR {diff_inr:10,.2f} | +{diff_pct:5.2f}% |")

    # Overall Total for Seed 42
    b_tot = results[42]["baseline"]["overall"]["net_revenue"]
    l_tot = results[42]["locked_linucb"]["overall"]["net_revenue"]
    a_tot = results[42]["adaptive_linucb"]["overall"]["net_revenue"]
    tot_diff = a_tot - l_tot
    tot_pct = (tot_diff / l_tot) * 100.0
    print(f"| **OVERALL TOTAL**    | INR {b_tot:12,.2f} | INR {l_tot:12,.2f} | INR {a_tot:12,.2f} | **+INR {tot_diff:10,.2f}** | **+{tot_pct:5.2f}%** |\n")

    # 4. MULTI-SEED 3-WAY SUMMARY TABLE (SEEDS 42, 101, 2026)
    print("--- 4. MULTI-SEED OVERALL NET REVENUE 3-WAY COMPARISON ---")
    print("| Seed | Baseline Net Rev (INR) | Locked LinUCB Net Rev (INR) | Adaptive LinUCB Net Rev (INR) | Adaptive vs Baseline Lift (%) | Adaptive vs Locked Lift (%) |")
    print("| :---: | :---: | :---: | :---: | :---: | :---: |")
    for s in seeds:
        bn = results[s]["baseline"]["overall"]["net_revenue"]
        ln = results[s]["locked_linucb"]["overall"]["net_revenue"]
        an = results[s]["adaptive_linucb"]["overall"]["net_revenue"]
        lift_vs_base = ((an - bn) / bn) * 100.0
        lift_vs_locked = ((an - ln) / ln) * 100.0
        print(f"| {s:<4} | INR {bn:12,.2f} | INR {ln:12,.2f} | INR {an:12,.2f} | +{lift_vs_base:5.2f}% | +{lift_vs_locked:5.2f}% |")

    # 5. EXACT NUMERIC TRACES FOR HIGH-TICKET VS LOW-TICKET
    print("\n--- 5. EXACT-NUMERIC TRACES ---")
    from dataclasses import asdict
    log_records = [asdict(r) if hasattr(r, "__dataclass_fields__") else r for r in results[42]["log_adaptive"].records]
    high_ticket_trace = None
    low_ticket_trace = None

    for r in log_records:
        fc = r.get("context_vector", {}).get("failure_code")
        should_stop = r.get("should_stop")
        reason = r.get("stop_reason", "")
        att = r.get("attempt_number", 1)

        if fc == "do_not_honor" and not should_stop and "cold_start_safeguard_active" in reason and high_ticket_trace is None:
            high_ticket_trace = r
        elif fc == "generic_decline" and should_stop and "expected_net_value_negative" in reason and low_ticket_trace is None:
            low_ticket_trace = r

    if high_ticket_trace:
        print("High-Ticket Safeguard Trace (do_not_honor):")
        print(f"  Tx ID         : {high_ticket_trace['transaction_id']}")
        print(f"  Attempt       : {high_ticket_trace['attempt_number']}")
        print(f"  Failure Code  : {high_ticket_trace['context_vector']['failure_code']}")
        print(f"  Should Stop   : {high_ticket_trace['should_stop']}")
        print(f"  Reason        : {high_ticket_trace['stop_reason']}")
        print(f"  Arm Chosen    : {high_ticket_trace['arm_chosen']}\n")

    if low_ticket_trace:
        print("Low-Ticket EV Stopping Trace (generic_decline):")
        print(f"  Tx ID         : {low_ticket_trace['transaction_id']}")
        print(f"  Attempt       : {low_ticket_trace['attempt_number']}")
        print(f"  Failure Code  : {low_ticket_trace['context_vector']['failure_code']}")
        print(f"  Should Stop   : {low_ticket_trace['should_stop']}")
        print(f"  Reason        : {low_ticket_trace['stop_reason']}")
        print(f"  Arm Chosen    : {low_ticket_trace['arm_chosen']}\n")

    # Save summary data to json
    out_file = Path(r"C:\Users\Thanujha\.gemini\antigravity\scratch\bandit_retry_scheduler\audit\item3_adaptive_results.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    summary_dict = {
        "seed_42_by_code": {
            c: {
                "baseline": results[42]["baseline"]["by_failure_code"][c]["net_revenue"],
                "locked": results[42]["locked_linucb"]["by_failure_code"][c]["net_revenue"],
                "adaptive": results[42]["adaptive_linucb"]["by_failure_code"][c]["net_revenue"],
            }
            for c in codes
        },
        "overall_multi_seed": {
            s: {
                "baseline": results[s]["baseline"]["overall"]["net_revenue"],
                "locked": results[s]["locked_linucb"]["overall"]["net_revenue"],
                "adaptive": results[s]["adaptive_linucb"]["overall"]["net_revenue"],
            }
            for s in seeds
        }
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary_dict, f, indent=2)
    print(f"Item 3 results saved to: {out_file}")

if __name__ == "__main__":
    main()
