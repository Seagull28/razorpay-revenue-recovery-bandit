"""
test_simulator.py
Unit and validation tests for Phase 1 Synthetic Data Simulator.
Verifies:
1. Probabilities respond sensibly to delay arms and contexts (e.g. timeout peaks early, insufficient funds peaks late).
2. Bank D drift triggers starting at simulated day >= 20 for do_not_honor.
3. card_expired strictly produces 0.0 recovery across all arms, banks, and modifiers.
4. Amount distributions conform to explicit mapping (standard vs high-ticket).
5. Modifiers (network, customer success, folded cycle failure fatigue) behave as intended.
6. simulate_retry functional and class interfaces execute and return valid results.
7. Stream generator creates structured valid transaction streams across 30 days.
"""

import numpy as np
import pytest

from bandit_retry_scheduler.simulator.config import (
    AMOUNT_DISTRIBUTION_MAPPING,
    BANK_D_DRIFT_DAY,
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


class TestGroundTruthProbabilities:
    """Tests evaluating true recovery probability logic."""

    def test_base_recovery_probabilities_completeness_100_combinations(self):
        """Assert that all 100 (5 failure codes x 4 banks x 5 delay arms) combinations are explicitly defined."""
        from bandit_retry_scheduler.simulator.config import FAILURE_CODES, BANKS, DELAY_ARMS
        for code in FAILURE_CODES:
            assert code in BASE_RECOVERY_PROBABILITIES, f"Failure code '{code}' missing from BASE_RECOVERY_PROBABILITIES"
            for bank in BANKS:
                assert bank in BASE_RECOVERY_PROBABILITIES[code], f"Bank '{bank}' missing from BASE_RECOVERY_PROBABILITIES[{code}]"
                for delay in DELAY_ARMS:
                    assert delay in BASE_RECOVERY_PROBABILITIES[code][bank], f"Delay '{delay}' missing from BASE_RECOVERY_PROBABILITIES[{code}][{bank}]"

    def test_bank_b_insufficient_funds_exact_values(self):
        """Verify Bank B insufficient_funds matches the exact ground-truth values from Section 4.6."""
        context = {
            "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
            "bank": Bank.BANK_B.value,
            "network": Network.MASTERCARD.value,  # multiplier 1.0
            "customer_prior_success_count": "1-3",  # multiplier 1.0
            "customer_prior_failures_this_cycle": "0",  # multiplier 1.0
            "day_of_month_bucket": "mid",  # salary multiplier 1.0
            "simulated_day": 10,
        }

        expected_probs = {"1hr": 0.05, "6hr": 0.08, "1d": 0.15, "3d": 0.45, "7d": 0.30}
        for arm, expected_p in expected_probs.items():
            p = calculate_recovery_probability(context, arm)
            assert pytest.approx(p, 0.0001) == expected_p

    def test_card_expired_always_zero(self):
        """Verify card_expired has strictly 0.0 recovery at every delay, across all banks and modifiers."""
        for bank in [Bank.BANK_A.value, Bank.BANK_B.value, Bank.BANK_C.value, Bank.BANK_D.value]:
            for arm in DELAY_ARMS:
                for success in ["0", "1-3", "4+"]:
                    for failure in ["0", "1", "2+"]:
                        for net in [Network.VISA.value, Network.MASTERCARD.value, Network.RUPAY.value]:
                            ctx = {
                                "failure_code": FailureCode.CARD_EXPIRED.value,
                                "bank": bank,
                                "network": net,
                                "customer_prior_success_count": success,
                                "customer_prior_failures_this_cycle": failure,
                                "day_of_month_bucket": "early",
                                "simulated_day": 25,
                            }
                            assert calculate_recovery_probability(ctx, arm) == 0.0

    def test_issuer_timeout_peaks_at_fast_retry(self):
        """Issuer timeouts should have highest recovery on quick retries (1hr) and decay later."""
        context = {
            "failure_code": FailureCode.ISSUER_TIMEOUT.value,
            "bank": Bank.BANK_C.value,  # timeout-prone bank
            "network": Network.VISA.value,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "mid",
            "simulated_day": 5,
        }

        p_1hr = calculate_recovery_probability(context, "1hr")
        p_6hr = calculate_recovery_probability(context, "6hr")
        p_1d = calculate_recovery_probability(context, "1d")
        p_3d = calculate_recovery_probability(context, "3d")
        p_7d = calculate_recovery_probability(context, "7d")

        # Monotonic decay for issuer timeout
        assert p_1hr > p_6hr > p_1d > p_3d > p_7d
        assert p_1hr > 0.70  # Bank C is heavily timeout-recoverable

    def test_bank_d_drift_after_day_20(self):
        """Bank D do_not_honor recovery rate should loosen dramatically starting at simulated day 20."""
        ctx_pre_drift = {
            "failure_code": FailureCode.DO_NOT_HONOR.value,
            "bank": Bank.BANK_D.value,
            "network": Network.MASTERCARD.value,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "mid",
            "simulated_day": 19,
        }

        ctx_post_drift = {
            "failure_code": FailureCode.DO_NOT_HONOR.value,
            "bank": Bank.BANK_D.value,
            "network": Network.MASTERCARD.value,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "mid",
            "simulated_day": 20,
        }

        # Pre-drift day 19: do_not_honor is rare/low recovery
        p_pre_1d = calculate_recovery_probability(ctx_pre_drift, "1d")
        assert p_pre_1d <= 0.06

        # Post-drift day 20: do_not_honor jumps significantly (e.g. ~0.52 for 1d)
        p_post_1d = calculate_recovery_probability(ctx_post_drift, "1d")
        assert p_post_1d >= 0.50
        assert p_post_1d > (p_pre_1d * 8)

    def test_bank_b_salary_day_boost(self):
        """Bank B insufficient funds should receive a salary boost in 'early' day of month."""
        ctx_mid = {
            "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
            "bank": Bank.BANK_B.value,
            "network": Network.MASTERCARD.value,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "mid",
        }
        ctx_early = {
            "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
            "bank": Bank.BANK_B.value,
            "network": Network.MASTERCARD.value,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "early",
        }

        p_mid_3d = calculate_recovery_probability(ctx_mid, "3d")
        p_early_3d = calculate_recovery_probability(ctx_early, "3d")
        assert p_early_3d > p_mid_3d

    def test_network_modifiers(self):
        """Visa retries succeed slightly more often than Mastercard, which succeeds more than RuPay."""
        base_ctx = {
            "failure_code": FailureCode.GENERIC_DECLINE.value,
            "bank": Bank.BANK_A.value,
            "customer_prior_success_count": "1-3",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "mid",
        }

        p_visa = calculate_recovery_probability({**base_ctx, "network": Network.VISA.value}, "1d")
        p_mc = calculate_recovery_probability({**base_ctx, "network": Network.MASTERCARD.value}, "1d")
        p_rupay = calculate_recovery_probability({**base_ctx, "network": Network.RUPAY.value}, "1d")

        assert p_visa > p_mc > p_rupay

    def test_cycle_failure_fatigue_modifier(self):
        """Folded cycle failure fatigue: repeated failures in current cycle penalize recovery probability."""
        base_ctx = {
            "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
            "bank": Bank.BANK_A.value,
            "network": Network.MASTERCARD.value,
            "customer_prior_success_count": "1-3",
            "day_of_month_bucket": "mid",
        }

        p_fail0 = calculate_recovery_probability({**base_ctx, "customer_prior_failures_this_cycle": "0"}, "3d")
        p_fail1 = calculate_recovery_probability({**base_ctx, "customer_prior_failures_this_cycle": "1"}, "3d")
        p_fail2 = calculate_recovery_probability({**base_ctx, "customer_prior_failures_this_cycle": "2+"}, "3d")

        assert p_fail0 > p_fail1 > p_fail2


class TestAmountDistributions:
    """Tests checking explicit mapping of failure codes to amount distributions."""

    def test_explicit_mapping_definitions(self):
        """Ensure all 5 failure codes are explicitly mapped as required by user instruction #2."""
        assert AMOUNT_DISTRIBUTION_MAPPING[FailureCode.ISSUER_TIMEOUT.value] == "standard"
        assert AMOUNT_DISTRIBUTION_MAPPING[FailureCode.GENERIC_DECLINE.value] == "standard"
        assert AMOUNT_DISTRIBUTION_MAPPING[FailureCode.CARD_EXPIRED.value] == "standard"
        assert AMOUNT_DISTRIBUTION_MAPPING[FailureCode.INSUFFICIENT_FUNDS.value] == "high_ticket"
        assert AMOUNT_DISTRIBUTION_MAPPING[FailureCode.DO_NOT_HONOR.value] == "high_ticket"

    def test_amount_sampling_statistics(self):
        """Sample amounts and verify median/mean for standard vs high-ticket distributions."""
        sim = RetrySimulator(seed=123)
        n_samples = 1000

        std_amounts = [sim.sample_amount(FailureCode.ISSUER_TIMEOUT.value) for _ in range(n_samples)]
        high_amounts = [sim.sample_amount(FailureCode.INSUFFICIENT_FUNDS.value) for _ in range(n_samples)]

        median_std = np.median(std_amounts)
        median_high = np.median(high_amounts)

        # Standard median should be around ₹1,500 (+/- 25%)
        assert 1200 <= median_std <= 1800
        # High-ticket median should be around ₹5,000 (+/- 25%)
        assert 4000 <= median_high <= 6000
        # High ticket amounts should be significantly larger on average
        assert np.mean(high_amounts) > np.mean(std_amounts) * 2.5


class TestSimulatorEnvironment:
    """Tests checking simulate_retry execution and outputs."""

    def test_simulate_retry_card_expired_never_succeeds(self):
        """Card expired retry should always return success=False, amount_recovered=0.0."""
        ctx = {
            "failure_code": FailureCode.CARD_EXPIRED.value,
            "bank": Bank.BANK_A.value,
            "network": Network.VISA.value,
            "amount": 2500.0,
        }
        for arm in DELAY_ARMS:
            for _ in range(50):
                success, amount_recovered = simulate_retry(ctx, arm)
                assert success is False
                assert amount_recovered == 0.0

    def test_simulate_retry_success_recovers_exact_amount(self):
        """When retry succeeds, amount_recovered should exactly equal the transaction amount."""
        sim = RetrySimulator(seed=42)
        ctx = {
            "failure_code": FailureCode.ISSUER_TIMEOUT.value,
            "bank": Bank.BANK_C.value,
            "network": Network.VISA.value,
            "customer_prior_success_count": "4+",
            "customer_prior_failures_this_cycle": "0",
            "amount": 4999.50,
        }
        # Run multiple trials; at least one will succeed
        successes = 0
        for _ in range(50):
            success, amount_recovered = sim.simulate_retry(ctx, "1hr")
            if success:
                successes += 1
                assert amount_recovered == 4999.50
            else:
                assert amount_recovered == 0.0
        assert successes > 30  # High recovery rate for Bank C timeout on 1hr

    def test_simulate_retry_dynamic_sampling_and_medians(self):
        """
        Verify that simulate_retry draws amount_recovered dynamically from the
        per-failure-code log-normal distributions in config.py (not a fixed placeholder),
        and that issuer_timeout (~INR 1,500) and insufficient_funds (~INR 5,000)
        differ significantly and match their respective expected medians over many draws.
        """
        sim = RetrySimulator(seed=2026)
        n_draws = 2000

        recovered_timeout = []
        recovered_insufficient = []

        # Run draws for issuer_timeout (standard distribution, ~INR 1,500 median)
        ctx_timeout = {
            "failure_code": FailureCode.ISSUER_TIMEOUT.value,
            "bank": Bank.BANK_A.value,
            "network": Network.VISA.value,
            "customer_prior_success_count": "4+",
            "customer_prior_failures_this_cycle": "0",
        }
        for _ in range(n_draws):
            # Pass fresh context without 'amount' so simulate_retry draws dynamically
            c = dict(ctx_timeout)
            success, amount_rec = sim.simulate_retry(c, "1hr")
            if success:
                recovered_timeout.append(amount_rec)

        # Run draws for insufficient_funds (high-ticket distribution, ~INR 5,000 median)
        ctx_insufficient = {
            "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
            "bank": Bank.BANK_B.value,
            "network": Network.VISA.value,
            "customer_prior_success_count": "4+",
            "customer_prior_failures_this_cycle": "0",
            "day_of_month_bucket": "early",
        }
        for _ in range(n_draws):
            # Pass fresh context without 'amount' so simulate_retry draws dynamically
            c = dict(ctx_insufficient)
            success, amount_rec = sim.simulate_retry(c, "3d")
            if success:
                recovered_insufficient.append(amount_rec)

        assert len(recovered_timeout) > 500
        assert len(recovered_insufficient) > 500

        # Assert variance: amounts are not constant placeholders
        assert len(set(recovered_timeout)) > 100
        assert len(set(recovered_insufficient)) > 100

        median_timeout = float(np.median(recovered_timeout))
        median_insufficient = float(np.median(recovered_insufficient))

        # Expected medians: ~INR 1,500 for standard, ~INR 5,000 for high-ticket (within 15% tolerance)
        assert 1300.0 <= median_timeout <= 1700.0, f"Expected timeout median ~1500, got {median_timeout}"
        assert 4300.0 <= median_insufficient <= 5700.0, f"Expected insufficient median ~5000, got {median_insufficient}"

        # Assert significant difference between standard and high-ticket
        assert median_insufficient > median_timeout * 2.5
        assert np.mean(recovered_insufficient) > np.mean(recovered_timeout) * 2.5

    def test_invalid_delay_raises_value_error(self):
        """Invalid delay arm must raise ValueError."""
        sim = RetrySimulator()
        with pytest.raises(ValueError):
            sim.simulate_retry({"failure_code": "generic_decline"}, "2weeks")


class TestStreamGenerator:
    """Tests validating the synthetic transaction stream generator over 30 days."""

    def test_stream_schema_and_features(self):
        generator = TransactionStreamGenerator(seed=42)
        stream = generator.generate_stream(num_days=30, transactions_per_day=20)

        assert len(stream) == 600

        for tx in stream:
            # Check 7 context features (Section 4.5)
            assert tx["failure_code"] in [f.value for f in FailureCode]
            assert tx["bank"] in [b.value for b in Bank]
            assert tx["network"] in [n.value for n in Network]
            assert tx["retry_attempt_number"] == 1
            assert tx["day_of_month_bucket"] in ["early", "mid", "late"]
            assert tx["customer_prior_success_count"] in ["0", "1-3", "4+"]
            assert tx["customer_prior_failures_this_cycle"] in ["0", "1", "2+"]

            # Metadata
            assert tx["transaction_id"].startswith("tx_")
            assert tx["amount"] > 0.0
            assert 1 <= tx["simulated_day"] <= 30
            assert 1 <= tx["day_of_month"] <= 31

    def test_iter_stream(self):
        generator = TransactionStreamGenerator(seed=99)
        count = sum(1 for _ in generator.iter_stream(num_days=5, transactions_per_day=10))
        assert count == 50
