"""
generate_exact_three_traces.py
Generates the 3 exact-numeric traces requested by the user:
1. Trace A: High-ticket do_not_honor transaction continuing on positive EV (max theta^T x > 0).
2. Trace B: Low-ticket/degraded transaction stopping early on Attempt 2 due to negative EV (max theta^T x <= 0).
3. Trace C: Boundary case near zero EV showing the exact point estimates driving continuation vs stopping.
"""

from pathlib import Path
import sys
import numpy as np

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.config import Bank, DelayArm, FailureCode, Network
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator


def setup_mature_policy(min_samples: int = 15):
    # Train on 600 transactions so models across arms/contexts have mature theta estimates
    generator = TransactionStreamGenerator(seed=42)
    warmup_stream = generator.generate_stream(num_days=6, transactions_per_day=100)

    sim = RetrySimulator(seed=42)
    policy = LinUCBPolicy(alpha=1.0, stopping_mode="expected_value", min_samples_for_stopping=min_samples, max_attempts=4)
    engine = PolicyExecutionEngine(simulator=sim, retry_cost=10.0)
    logger = AuditLogger()
    engine.run(transactions=warmup_stream, policy=policy, logger=logger)
    return policy


def run_and_print_traces():
    policy = setup_mature_policy(min_samples=15)
    sim = RetrySimulator(seed=999)

    # -------------------------------------------------------------------------
    # TRACE 1: High-ticket do_not_honor (INR 6,500) -> Positive EV -> Continues
    # -------------------------------------------------------------------------
    tx_high = {
        "transaction_id": "tx_trace_high_ev_dnh",
        "customer_id": "cust_high_dnh",
        "failure_code": FailureCode.DO_NOT_HONOR.value,
        "bank": Bank.BANK_A.value,
        "network": Network.VISA.value,
        "amount": 6500.00,
        "simulated_day": 7,
        "day_of_month": 7,
        "day_of_month_bucket": "early",
        "retry_attempt_number": 1,
        "customer_prior_success_count": "1-3",
        "customer_prior_failures_this_cycle": "0",
    }

    # -------------------------------------------------------------------------
    # TRACE 2: Low-ticket degraded transaction -> Negative EV on Attempt 2 -> Stops
    # (generic_decline on Bank D with multiple prior cycle failures and low ticket)
    # -------------------------------------------------------------------------
    tx_stop = {
        "transaction_id": "tx_trace_neg_ev_stop",
        "customer_id": "cust_neg_ev",
        "failure_code": FailureCode.GENERIC_DECLINE.value,
        "bank": Bank.BANK_D.value,
        "network": Network.RUPAY.value,
        "amount": 180.00,
        "simulated_day": 8,
        "day_of_month": 8,
        "day_of_month_bucket": "early",
        "retry_attempt_number": 1,
        "customer_prior_success_count": "0",
        "customer_prior_failures_this_cycle": "2+",
    }

    # -------------------------------------------------------------------------
    # TRACE 3: Near-zero boundary transaction
    # (generic_decline on Bank B with 1 failure in cycle)
    # -------------------------------------------------------------------------
    tx_boundary = {
        "transaction_id": "tx_trace_boundary_ev",
        "customer_id": "cust_boundary",
        "failure_code": FailureCode.GENERIC_DECLINE.value,
        "bank": Bank.BANK_B.value,
        "network": Network.MASTERCARD.value,
        "amount": 450.00,
        "simulated_day": 9,
        "day_of_month": 9,
        "day_of_month_bucket": "early",
        "retry_attempt_number": 1,
        "customer_prior_success_count": "0",
        "customer_prior_failures_this_cycle": "1",
    }

    def execute_and_log(tx_dict, label):
        print("=" * 105)
        print(f"EXACT-NUMERIC TRACE: {label}")
        print("=" * 105)
        curr_ctx = dict(tx_dict)
        attempt = 1
        prev_success = False

        while True:
            # Check stopping rules
            stop, reason = policy.should_stop(curr_ctx, attempt_number=attempt, previous_success=prev_success)
            scores = policy.get_arm_scores(curr_ctx)
            best_ev_arm = max(scores.keys(), key=lambda a: scores[a]["theta_dot_x"])
            max_ev = scores[best_ev_arm]["theta_dot_x"]

            print(f"\n[Attempt #{attempt}] (Simulated Day {curr_ctx['simulated_day']}, {curr_ctx['day_of_month_bucket']} bucket)")
            print(f" Context: failure_code='{curr_ctx['failure_code']}', bank='{curr_ctx['bank']}', network='{curr_ctx['network']}', prior_fails='{curr_ctx['customer_prior_failures_this_cycle']}', amount=INR {curr_ctx['amount']:,.2f}")
            print(f" All 5 Arms Evaluated (Numeric Point Estimates & Exploration Bonuses):")
            print(f"   {'Arm':<6} | {'Point Est (theta^T x)':<24} | {'Bonus (alpha*sqrt)':<20} | {'UCB Score':<15} | {'Pull Count':<10}")
            print(f"   {'-'*88}")
            for arm in ["1hr", "6hr", "1d", "3d", "7d"]:
                d = scores[arm]
                marker = " <-- [MAX EV]" if arm == best_ev_arm else ""
                print(f"   {arm:<6} | INR {d['theta_dot_x']:>18.4f} | {d['bonus']:>20.4f} | {d['ucb_score']:>15.4f} | {d['pull_count']:>10}{marker}")
            
            print(f" Continuation Evaluation: max_a (theta_a^T x) = INR {max_ev:.4f} (Rule: > 0 => Continue, <= 0 => Stop)")
            print(f" Stopping Decision      : {'STOP RETRYING' if stop else 'CONTINUE RETRYING'} (Reason: {reason})")

            if stop:
                print(f" Result                 : RETRY TERMINATED BY POLICY.")
                break

            decision = policy.select_arm(curr_ctx, attempt_number=attempt)
            chosen_arm = decision.arm_chosen
            true_p = sim.get_true_recovery_probability(curr_ctx, chosen_arm)
            success, amount_rec = sim.simulate_retry(curr_ctx, chosen_arm)
            reward = (amount_rec if success else 0.0) - 10.0

            print(f" Selected Delay (Arm)   : {chosen_arm} (argmax UCB = {decision.expected_value:.4f})")
            print(f" True Probability       : {true_p:.6f} ({true_p*100:.2f}%)")
            print(f" Attempt Outcome        : {'SUCCESS (RECOVERED)' if success else 'FAILED'} (Reward: INR {reward:,.2f})")

            # Update policy
            policy.update(curr_ctx, chosen_arm, reward)

            if success:
                print(f" Result                 : TRANSACTION FULLY RECOVERED.")
                break

            from bandit_retry_scheduler.runner.engine import advance_transaction_context
            curr_ctx = advance_transaction_context(curr_ctx, chosen_arm)
            attempt += 1

        print("-" * 105)

    execute_and_log(tx_high, "Trace 1: High-Ticket do_not_honor (INR 6,500) — Positive EV Retries")
    execute_and_log(tx_stop, "Trace 2: Low-Ticket Degraded History — Negative EV Stops Early on Attempt 2")
    execute_and_log(tx_boundary, "Trace 3: Boundary Case — Precision Point Estimate Transition")


if __name__ == "__main__":
    run_and_print_traces()
