"""
encoder.py
Numeric feature vector encoding for contextual bandits (LinUCB).
Converts the 7-feature transaction context into a fixed 19-dimensional numpy array.
"""

from typing import Any, Dict, List
import numpy as np

from bandit_retry_scheduler.simulator.config import (
    BANKS,
    DAY_OF_MONTH_BUCKETS,
    FAILURE_CODES,
    NETWORKS,
    Bank,
    FailureCode,
    Network,
)
from bandit_retry_scheduler.simulator.ground_truth import to_day_bucket, to_failure_bucket, to_success_bucket


class ContextVectorEncoder:
    """
    Encodes transaction context dictionary into a 19-dimensional numeric feature vector.

    =============================================================================
    FEATURE VECTOR SPECIFICATION (Total Dimension d = 19):
    =============================================================================
    1-5:   failure_code (one-hot, 5 dims)
           [insufficient_funds, issuer_timeout, do_not_honor, card_expired, generic_decline]
    6-9:   bank (one-hot, 4 dims)
           [Bank A, Bank B, Bank C, Bank D]
    10-12: network (one-hot, 3 dims)
           [Visa, Mastercard, RuPay]
    13-15: day_of_month_bucket (one-hot, 3 dims)
           [early, mid, late]
    16:    retry_attempt_number (numeric normalized, 1 dim): (attempt - 1) / 3.0 in [0.0, 1.0]
    17:    customer_prior_success_count (numeric ordinal, 1 dim): '0'->0.0, '1-3'->0.5, '4+'->1.0
    18:    customer_prior_failures_this_cycle (numeric ordinal, 1 dim): '0'->0.0, '1'->0.5, '2+'->1.0
    19:    bias / intercept term (1 dim): 1.0
    =============================================================================
    """

    DIMENSION: int = 19

    FAILURE_CODE_LIST: List[str] = [
        FailureCode.INSUFFICIENT_FUNDS.value,
        FailureCode.ISSUER_TIMEOUT.value,
        FailureCode.DO_NOT_HONOR.value,
        FailureCode.CARD_EXPIRED.value,
        FailureCode.GENERIC_DECLINE.value,
    ]

    BANK_LIST: List[str] = [
        Bank.BANK_A.value,
        Bank.BANK_B.value,
        Bank.BANK_C.value,
        Bank.BANK_D.value,
    ]

    NETWORK_LIST: List[str] = [
        Network.VISA.value,
        Network.MASTERCARD.value,
        Network.RUPAY.value,
    ]

    DAY_BUCKET_LIST: List[str] = ["early", "mid", "late"]

    SUCCESS_ORDINAL_MAP: Dict[str, float] = {
        "0": 0.0,
        "1-3": 0.5,
        "4+": 1.0,
    }

    FAILURE_ORDINAL_MAP: Dict[str, float] = {
        "0": 0.0,
        "1": 0.5,
        "2+": 1.0,
    }

    def encode(self, context: Dict[str, Any]) -> np.ndarray:
        """
        Transforms context dictionary into a 19-dimensional float64 vector.
        """
        vec = np.zeros(self.DIMENSION, dtype=np.float64)
        idx = 0

        # 1. failure_code (one-hot, 5 dims)
        f_code = context.get("failure_code", FailureCode.GENERIC_DECLINE.value)
        for code in self.FAILURE_CODE_LIST:
            vec[idx] = 1.0 if f_code == code else 0.0
            idx += 1

        # 2. bank (one-hot, 4 dims)
        bank = context.get("bank", Bank.BANK_A.value)
        for b in self.BANK_LIST:
            vec[idx] = 1.0 if bank == b else 0.0
            idx += 1

        # 3. network (one-hot, 3 dims)
        net = context.get("network", Network.MASTERCARD.value)
        for n in self.NETWORK_LIST:
            vec[idx] = 1.0 if net == n else 0.0
            idx += 1

        # 4. day_of_month_bucket (one-hot, 3 dims)
        day_bucket = context.get("day_of_month_bucket")
        if not day_bucket and "day_of_month" in context:
            day_bucket = to_day_bucket(context["day_of_month"])
        elif not day_bucket:
            day_bucket = "mid"

        for db in self.DAY_BUCKET_LIST:
            vec[idx] = 1.0 if day_bucket == db else 0.0
            idx += 1

        # 5. retry_attempt_number (normalized, 1 dim)
        attempt = int(context.get("retry_attempt_number", 1))
        vec[idx] = max(0.0, min(1.0, (attempt - 1) / 3.0))
        idx += 1

        # 6. customer_prior_success_count (ordinal, 1 dim)
        succ_bucket = to_success_bucket(context.get("customer_prior_success_count", "1-3"))
        vec[idx] = self.SUCCESS_ORDINAL_MAP.get(succ_bucket, 0.5)
        idx += 1

        # 7. customer_prior_failures_this_cycle (ordinal, 1 dim)
        fail_bucket = to_failure_bucket(context.get("customer_prior_failures_this_cycle", "0"))
        vec[idx] = self.FAILURE_ORDINAL_MAP.get(fail_bucket, 0.0)
        idx += 1

        # 8. Bias / Intercept term (1 dim)
        vec[idx] = 1.0
        idx += 1

        assert idx == self.DIMENSION, f"Encoder index mismatch: expected {self.DIMENSION}, got {idx}"
        return vec
