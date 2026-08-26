"""
stream_generator.py
Generates a stream of synthetic failed transactions over a configurable time window (e.g. 30 days).
Provides structured contexts ready for evaluation of bandit and baseline policies.
"""

from typing import Any, Dict, Iterator, List, Optional
import uuid
import numpy as np

from bandit_retry_scheduler.simulator.config import (
    BANKS,
    FAILURE_CODES,
    NETWORKS,
    Bank,
    FailureCode,
    Network,
)
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.ground_truth import to_day_bucket, to_failure_bucket, to_success_bucket


class TransactionStreamGenerator:
    """
    Generates realistic streams of synthetic failed transactions across simulated days.
    """

    def __init__(self, seed: Optional[int] = 42):
        self.rng = np.random.default_rng(seed)
        self.simulator = RetrySimulator(seed=seed)

        # Realistic distributions across India payment ecosystem
        self.failure_code_weights = {
            FailureCode.INSUFFICIENT_FUNDS.value: 0.38,
            FailureCode.ISSUER_TIMEOUT.value: 0.24,
            FailureCode.GENERIC_DECLINE.value: 0.18,
            FailureCode.DO_NOT_HONOR.value: 0.12,
            FailureCode.CARD_EXPIRED.value: 0.08,
        }

        self.bank_weights = {
            Bank.BANK_A.value: 0.35,  # Large well-behaved private bank
            Bank.BANK_B.value: 0.25,  # Salary-heavy bank
            Bank.BANK_C.value: 0.25,  # Infrastructure timeout-prone bank
            Bank.BANK_D.value: 0.15,  # Strict risk / drift bank
        }

        self.network_weights = {
            Network.VISA.value: 0.45,
            Network.MASTERCARD.value: 0.35,
            Network.RUPAY.value: 0.20,
        }

        self.customer_success_weights = {
            "0": 0.20,
            "1-3": 0.50,
            "4+": 0.30,
        }

    def generate_transaction(
        self,
        simulated_day: int,
        day_of_month: Optional[int] = None,
        customer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generates a single synthetic failed transaction with all 7 context features and metadata.
        """
        if day_of_month is None:
            # Map simulated_day to 1..31 day-of-month cycle
            day_of_month = ((simulated_day - 1) % 31) + 1

        day_of_month_bucket = to_day_bucket(day_of_month)

        # Sample attributes
        failure_code = self.rng.choice(
            list(self.failure_code_weights.keys()),
            p=list(self.failure_code_weights.values()),
        )
        bank = self.rng.choice(
            list(self.bank_weights.keys()),
            p=list(self.bank_weights.values()),
        )
        network = self.rng.choice(
            list(self.network_weights.keys()),
            p=list(self.network_weights.values()),
        )
        prior_success_bucket = self.rng.choice(
            list(self.customer_success_weights.keys()),
            p=list(self.customer_success_weights.values()),
        )

        amount = self.simulator.sample_amount(failure_code)
        tx_id = f"tx_{uuid.UUID(bytes=self.rng.bytes(16)).hex[:10]}"
        cust_id = customer_id or f"cust_{self.rng.integers(1000, 9999)}"

        context = {
            # 7 Context Vector Features (Section 4.5)
            "failure_code": str(failure_code),
            "bank": str(bank),
            "network": str(network),
            "retry_attempt_number": 1,
            "day_of_month_bucket": day_of_month_bucket,
            "customer_prior_success_count": prior_success_bucket,
            "customer_prior_failures_this_cycle": "0",
            # Additional metadata for simulation/tracking
            "transaction_id": tx_id,
            "customer_id": cust_id,
            "amount": amount,
            "simulated_day": int(simulated_day),
            "day_of_month": int(day_of_month),
        }
        return context

    def generate_stream(
        self,
        num_days: int = 30,
        transactions_per_day: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Generates a complete list of transactions over the simulated period.
        """
        stream: List[Dict[str, Any]] = []
        for day in range(1, num_days + 1):
            day_of_month = ((day - 1) % 31) + 1
            for _ in range(transactions_per_day):
                stream.append(self.generate_transaction(simulated_day=day, day_of_month=day_of_month))
        return stream

    def iter_stream(
        self,
        num_days: int = 30,
        transactions_per_day: int = 100,
    ) -> Iterator[Dict[str, Any]]:
        """
        Yields transactions one by one across the simulated period.
        """
        for day in range(1, num_days + 1):
            day_of_month = ((day - 1) % 31) + 1
            for _ in range(transactions_per_day):
                yield self.generate_transaction(simulated_day=day, day_of_month=day_of_month)
