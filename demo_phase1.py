import sys
from pathlib import Path

# Ensure root scratch directory is in python path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bandit_retry_scheduler.simulator.config import (
    AMOUNT_DISTRIBUTION_MAPPING,
    BANK_D_DRIFT_PROBABILITIES,
    BASE_RECOVERY_PROBABILITIES,
    DELAY_ARMS,
    Bank,
    DelayArm,
    FailureCode,
    Network,
)
from bandit_retry_scheduler.simulator.environment import RetrySimulator, simulate_retry
from bandit_retry_scheduler.simulator.ground_truth import calculate_recovery_probability
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator


def print_ground_truth_matrix():
    print("=" * 80)
    print("HIDDEN GROUND-TRUTH RECOVERY PROBABILITIES P(recover | failure_code, bank, delay)")
    print("=" * 80)
    header = f"{'Failure Code':<20} | {'Bank':<10} | " + " | ".join(f"{arm:>5}" for arm in DELAY_ARMS)
    print(header)
    print("-" * len(header))

    for code, bank_dict in BASE_RECOVERY_PROBABILITIES.items():
        for bank, delays in bank_dict.items():
            vals = " | ".join(f"{delays.get(arm, 0.0)*100:>4.1f}%" for arm in DELAY_ARMS)
            print(f"{code:<20} | {bank:<10} | {vals}")
        print("-" * len(header))

    print("\n[Bank D Drift: Starting at Day >= 20, 'do_not_honor' shifts]:")
    drift_vals = " | ".join(f"{BANK_D_DRIFT_PROBABILITIES.get(arm, 0.0)*100:>4.1f}%" for arm in DELAY_ARMS)
    print(f"{'do_not_honor (Day 20+)':<20} | {'Bank D':<10} | {drift_vals}")
    print("=" * 80)


def print_amount_mapping():
    print("\n" + "=" * 80)
    print("FAILURE CODE TO TRANSACTION AMOUNT DISTRIBUTION MAPPING (Section 4.8)")
    print("=" * 80)
    for code, dist_type in AMOUNT_DISTRIBUTION_MAPPING.items():
        desc = "INR 1,500 median (~INR 500 - INR 5,000)" if dist_type == "standard" else "INR 5,000 median (~INR 1,500 - INR 25,000)"
        print(f" - {code:<20} -> {dist_type.upper():<12} ({desc})")
    print("=" * 80)


def print_sample_simulation_runs():
    print("\n" + "=" * 80)
    print("SAMPLE RETRY SIMULATION EXECUTION")
    print("=" * 80)
    sim = RetrySimulator(seed=42)

    scenarios = [
        ("Issuer Timeout (Bank C, quick 1hr retry)", {
            "failure_code": FailureCode.ISSUER_TIMEOUT.value,
            "bank": Bank.BANK_C.value,
            "network": Network.VISA.value,
            "customer_prior_success_count": "4+",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "mid",
            "simulated_day": 5,
        }, "1hr"),
        ("Insufficient Funds (Bank B, early month payday 3d retry)", {
            "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
            "bank": Bank.BANK_B.value,
            "network": Network.MASTERCARD.value,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "early",
            "simulated_day": 2,
        }, "3d"),
        ("Card Expired (Bank A, attempt retry)", {
            "failure_code": FailureCode.CARD_EXPIRED.value,
            "bank": Bank.BANK_A.value,
            "network": Network.VISA.value,
            "customer_prior_success_count": "4+",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "mid",
            "simulated_day": 10,
        }, "1d"),
        ("Bank D Do-Not-Honor (Pre-drift: Day 15, 1d delay)", {
            "failure_code": FailureCode.DO_NOT_HONOR.value,
            "bank": Bank.BANK_D.value,
            "network": Network.MASTERCARD.value,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "mid",
            "simulated_day": 15,
        }, "1d"),
        ("Bank D Do-Not-Honor (Post-drift: Day 25, 1d delay)", {
            "failure_code": FailureCode.DO_NOT_HONOR.value,
            "bank": Bank.BANK_D.value,
            "network": Network.MASTERCARD.value,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "mid",
            "simulated_day": 25,
        }, "1d"),
    ]

    for title, ctx, delay in scenarios:
        true_p = sim.get_true_recovery_probability(ctx, delay)
        # Run 100 trials with dynamic log-normal amount sampling
        successes = 0
        total_recovered = 0.0
        recovered_amounts = []
        for _ in range(100):
            # fresh copy of ctx without hardcoded amount so simulator draws from lognormal distribution
            c = dict(ctx)
            succ, rec = sim.simulate_retry(c, delay)
            if succ:
                successes += 1
                total_recovered += rec
                recovered_amounts.append(rec)

        avg_recovered = (total_recovered / successes) if successes > 0 else 0.0
        print(f"\nScenario: {title}")
        print(f" - Delay Arm: {delay}")
        print(f" - True P(recover): {true_p*100:.1f}%")
        print(f" - 100 Trial Empirical Recovery: {successes}%")
        print(f" - Total Recovered: INR {total_recovered:,.2f} across {successes} successful retries")
        print(f" - Avg Recovered per Success: INR {avg_recovered:,.2f}")


def print_stream_summary():
    print("\n" + "=" * 80)
    print("30-DAY SYNTHETIC TRANSACTION STREAM GENERATION")
    print("=" * 80)
    generator = TransactionStreamGenerator(seed=42)
    stream = generator.generate_stream(num_days=30, transactions_per_day=50)

    print(f"Generated {len(stream)} failed transactions across 30 simulated days.")
    print("Sample generated transaction record:")
    sample = stream[0]
    for k, v in sample.items():
        print(f"  {k:<35}: {v}")
    print("=" * 80)


if __name__ == "__main__":
    print_ground_truth_matrix()
    print_amount_mapping()
    print_sample_simulation_runs()
    print_stream_summary()
