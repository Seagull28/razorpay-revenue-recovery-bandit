"""
generate_ev_traces.py
Extracts and prints 3 exact-numeric attempt-by-attempt traces evaluating
the new Expected-Value stopping rule:
(a) High-ticket do_not_honor transaction: continues retrying (positive EV).
(b) Low-ticket low-probability transaction: correctly stops early (negative EV).
(c) Boundary transaction: near zero EV showing exact theta^T x threshold driving decision.
"""

from pathlib import Path
import sys

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.config import Bank, FailureCode, Network
from bandit_retry_scheduler.simulator.environment import RetrySimulator


def generate_traces():
    # Pre-train a policy on 500 transactions so it has learned estimates
    from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator
    gen = TransactionStreamGenerator(seed=42)
    warmup_txs = gen.generate_stream(num_days=10, transactions_per_day=50)

    sim = RetrySimulator(seed=42)
    policy = LinUCBPolicy(alpha=1.0, stopping_mode="expected_value", min_samples_for_stopping=5, max_attempts=4)
    engine = PolicyExecutionEngine(simulator=sim, retry_cost=10.0)
    warmup_logger = AuditLogger()
    engine.run(transactions=warmup_txs, policy=policy, logger=warmup_logger)

    # =========================================================================
    # Scenario (a): High-ticket do_not_honor (Amount = INR 7,500)
    # Low probability (~4%), but 0.04 * 7500 - 10 = +INR 290 expected value -> CONTINUES
    # =========================================================================
    sim_a = RetrySimulator(seed=123)
    eng_a = PolicyExecutionEngine(simulator=sim_a, retry_cost=10.0)
    log_a = AuditLogger()
    tx_a = {
        "transaction_id": "tx_high_ticket_dnh",
        "customer_id": "cust_901",
        "failure_code": FailureCode.DO_NOT_HONOR.value,
        "bank": Bank.BANK_A.value,
        "network": Network.VISA.value,
        "amount": 7500.00,
        "simulated_day": 12,
        "day_of_month": 12,
        "day_of_month_bucket": "mid",
        "retry_attempt_number": 1,
        "customer_prior_success_count": "1-3",
        "customer_prior_failures_this_cycle": "0",
    }
    eng_a.process_transaction(tx_a, policy, log_a)

    # =========================================================================
    # Scenario (b): Low-ticket generic decline on RuPay (Amount = INR 120)
    # Even at 20% prob, 0.20 * 120 - 10 = +INR 14; with failure cycle penalty at attempt 2 (10%),
    # 0.10 * 120 - 10 = -INR 2 -> Negative EV -> STOPS EARLY on attempt 2
    # =========================================================================
    sim_b = RetrySimulator(seed=456)
    eng_b = PolicyExecutionEngine(simulator=sim_b, retry_cost=10.0)
    log_b = AuditLogger()
    tx_b = {
        "transaction_id": "tx_low_ticket_stop",
        "customer_id": "cust_902",
        "failure_code": FailureCode.DO_NOT_HONOR.value,
        "bank": Bank.BANK_B.value,
        "network": Network.RUPAY.value,
        "amount": 150.00,
        "simulated_day": 14,
        "day_of_month": 14,
        "day_of_month_bucket": "mid",
        "retry_attempt_number": 1,
        "customer_prior_success_count": "0",
        "customer_prior_failures_this_cycle": "0",
    }
    eng_b.process_transaction(tx_b, policy, log_b)

    # =========================================================================
    # Scenario (c): Boundary Case near EV = 0.0 (Amount = INR 280 on Bank A)
    # =========================================================================
    sim_c = RetrySimulator(seed=789)
    eng_c = PolicyExecutionEngine(simulator=sim_c, retry_cost=10.0)
    log_c = AuditLogger()
    tx_c = {
        "transaction_id": "tx_boundary_ev",
        "customer_id": "cust_903",
        "failure_code": FailureCode.DO_NOT_HONOR.value,
        "bank": Bank.BANK_A.value,
        "network": Network.MASTERCARD.value,
        "amount": 280.00,
        "simulated_day": 15,
        "day_of_month": 15,
        "day_of_month_bucket": "mid",
        "retry_attempt_number": 1,
        "customer_prior_success_count": "0",
        "customer_prior_failures_this_cycle": "0",
    }
    eng_c.process_transaction(tx_c, policy, log_c)

    return (log_a.to_records(), sim_a), (log_b.to_records(), sim_b), (log_c.to_records(), sim_c), policy


def print_ev_trace(title: str, records: list, simulator: RetrySimulator, policy: LinUCBPolicy):
    print("=" * 95)
    print(f"TRACE: {title}")
    print("=" * 95)
    for r in records:
        ctx = r["context_vector"]
        arm = r["arm_chosen"]
        att = ctx["retry_attempt_number"]
        scores = policy.get_arm_scores(ctx)
        best_ev_arm = max(scores.keys(), key=lambda a: scores[a]["theta_dot_x"])
        max_ev = scores[best_ev_arm]["theta_dot_x"]
        stop_decision, stop_reason = policy.should_stop(ctx, attempt_number=att, previous_success=False)
        exact_true_p = simulator.get_true_recovery_probability(ctx, arm)
        outcome_str = "SUCCESS (RECOVERED)" if r["actual_outcome"] == 1 else "FAILED"

        print(f"-> Attempt #{att}:")
        print(f"     Simulated Day       : Day {ctx['simulated_day']} (Day of Month: {ctx['day_of_month']}, Bucket: '{ctx['day_of_month_bucket']}')")
        print(f"     Failure Code / Bank : {ctx['failure_code']} / {ctx['bank']} ({ctx['network']})")
        print(f"     Amount              : INR {ctx['amount']:,.2f}")
        print(f"     Cycle Failures Prior: {ctx['customer_prior_failures_this_cycle']}")
        print(f"     Delay Chosen (Arm)  : {arm}")
        print(f"     True P(recover)     : {exact_true_p:.6f} ({exact_true_p * 100:.2f}%)")
        print(f"     Arm Breakdown (INR) :")
        for a in ["1hr", "6hr", "1d", "3d", "7d"]:
            marker = " <-- [BEST EV]" if a == best_ev_arm else ""
            print(f"       - {a:<4}: theta^T x = INR {scores[a]['theta_dot_x']:>8.2f} | Bonus = {scores[a]['bonus']:>6.2f} | UCB = {scores[a]['ucb_score']:>8.2f}{marker}")
        print(f"     Continuation Rule   : max_a (theta_a^T x) = INR {max_ev:.2f} (> 0: Continue, <= 0: Stop)")
        print(f"     Stopping Decision   : {'STOP' if stop_decision else 'CONTINUE'} (Reason: {stop_reason})")
        print(f"     Outcome / Reward    : {outcome_str} (Reward: INR {r['reward']:,.2f})")
        print("-" * 95)
    print()


if __name__ == "__main__":
    t_a, t_b, t_c, pol = generate_traces()
    print_ev_trace("Scenario (a): High-Ticket do_not_honor (INR 7,500) — Positive EV Continues", t_a[0], t_a[1], pol)
    print_ev_trace("Scenario (b): Low-Ticket do_not_honor (INR 150) — Negative EV Stops Early on Attempt 2", t_b[0], t_b[1], pol)
    print_ev_trace("Scenario (c): Boundary Case (INR 280) — Exact EV Threshold Driving Decision", t_c[0], t_c[1], pol)
