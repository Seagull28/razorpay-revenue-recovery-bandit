import json
from pathlib import Path
import sys

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bandit_retry_scheduler.audit.logger import AuditLogger
from bandit_retry_scheduler.policies.fixed_schedule import FixedSchedulePolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.config import Bank, FailureCode, Network
from bandit_retry_scheduler.simulator.environment import RetrySimulator


def generate_scenario_traces():
    policy = FixedSchedulePolicy(max_attempts=4)

    # Scenario 1: Succeeds on Attempt 1 (Bank B, insufficient funds, early month 1d retry)
    sim1 = RetrySimulator(seed=3)
    engine1 = PolicyExecutionEngine(simulator=sim1, retry_cost=10.0)
    logger1 = AuditLogger()
    tx1 = {
        "transaction_id": "tx_success_att1",
        "customer_id": "cust_8812",
        "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
        "bank": Bank.BANK_B.value,
        "network": Network.VISA.value,
        "amount": 5400.00,
        "simulated_day": 1,
        "day_of_month": 1,
        "day_of_month_bucket": "early",
        "retry_attempt_number": 1,
        "customer_prior_success_count": "4+",
        "customer_prior_failures_this_cycle": "0",
    }
    engine1.process_transaction(tx1, policy, logger1)

    # Scenario 2: Fails through all 4 attempts (Bank A, Do Not Honor, RuPay)
    sim2 = RetrySimulator(seed=999)
    engine2 = PolicyExecutionEngine(simulator=sim2, retry_cost=10.0)
    logger2 = AuditLogger()
    tx2 = {
        "transaction_id": "tx_fail_all4",
        "customer_id": "cust_3304",
        "failure_code": FailureCode.DO_NOT_HONOR.value,
        "bank": Bank.BANK_A.value,
        "network": Network.RUPAY.value,
        "amount": 4200.00,
        "simulated_day": 3,
        "day_of_month": 3,
        "day_of_month_bucket": "early",
        "retry_attempt_number": 1,
        "customer_prior_success_count": "0",
        "customer_prior_failures_this_cycle": "0",
    }
    engine2.process_transaction(tx2, policy, logger2)

    # Scenario 3: Bank D do_not_honor starting at Day 18, crossing Day 20 drift threshold mid-sequence
    sim3 = RetrySimulator(seed=0)
    engine3 = PolicyExecutionEngine(simulator=sim3, retry_cost=10.0)
    logger3 = AuditLogger()
    tx3 = {
        "transaction_id": "tx_bankd_drift",
        "customer_id": "cust_5129",
        "failure_code": FailureCode.DO_NOT_HONOR.value,
        "bank": Bank.BANK_D.value,
        "network": Network.VISA.value,
        "amount": 6500.00,
        "simulated_day": 18,
        "day_of_month": 18,
        "day_of_month_bucket": "mid",
        "retry_attempt_number": 1,
        "customer_prior_success_count": "4+",
        "customer_prior_failures_this_cycle": "0",
    }
    engine3.process_transaction(tx3, policy, logger3)

    return logger1.to_records(), logger2.to_records(), logger3.to_records(), sim1, sim2, sim3


def print_formatted_trace(title: str, records: list, simulator: RetrySimulator):
    print("=" * 85)
    print(f"TRACE: {title}")
    print("=" * 85)
    for r in records:
        ctx = r["context_vector"]
        arm = r["arm_chosen"]
        exact_true_p = simulator.get_true_recovery_probability(ctx, arm)
        outcome_str = "SUCCESS (RECOVERED)" if r["actual_outcome"] == 1 else "FAILED"
        print(f"-> Attempt #{ctx['retry_attempt_number']}:")
        print(f"     Simulated Day       : Day {ctx['simulated_day']} (Day of Month: {ctx['day_of_month']}, Bucket: '{ctx['day_of_month_bucket']}')")
        print(f"     Failure Code        : {ctx['failure_code']}")
        print(f"     Bank / Network      : {ctx['bank']} / {ctx['network']}")
        print(f"     Cycle Failures Prior: {ctx['customer_prior_failures_this_cycle']}")
        print(f"     Delay Chosen (Arm)  : {arm}")
        print(f"     True P(recover)     : {exact_true_p:.6f} ({exact_true_p * 100:.2f}%)")
        print(f"     Expected Value      : {r['expected_value']}")
        print(f"     Outcome             : {outcome_str}")
        print(f"     Amount Recovered    : INR {r['amount_recovered']:,.2f}")
        print(f"     Net Reward          : INR {r['reward']:,.2f}")
        print("-" * 85)
    print()


if __name__ == "__main__":
    t1, t2, t3, s1, s2, s3 = generate_scenario_traces()
    print_formatted_trace("1. Transaction Succeeds on Attempt 1", t1, s1)
    print_formatted_trace("2. Transaction Fails Through All 4 Attempts", t2, s2)
    print_formatted_trace("3. Transaction Crosses Bank D Day-20 Drift Mid-Sequence", t3, s3)
