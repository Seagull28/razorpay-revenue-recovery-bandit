"""
config.py
Configuration and domain definitions for the Bandit-Optimized Retry Scheduler simulator.
Adheres to Razorpay AI Buildathon 2026 (Track 3) Design Doc specifications.
"""

from enum import Enum
from typing import Dict, Literal


class FailureCode(str, Enum):
    INSUFFICIENT_FUNDS = "insufficient_funds"
    ISSUER_TIMEOUT = "issuer_timeout"
    DO_NOT_HONOR = "do_not_honor"
    CARD_EXPIRED = "card_expired"
    GENERIC_DECLINE = "generic_decline"


class Bank(str, Enum):
    BANK_A = "Bank A"
    BANK_B = "Bank B"
    BANK_C = "Bank C"
    BANK_D = "Bank D"


class Network(str, Enum):
    VISA = "Visa"
    MASTERCARD = "Mastercard"
    RUPAY = "RuPay"


class DelayArm(str, Enum):
    HOUR_1 = "1hr"
    HOUR_6 = "6hr"
    DAY_1 = "1d"
    DAY_3 = "3d"
    DAY_7 = "7d"


# List of ordered arms for bandit algorithms
DELAY_ARMS = [
    DelayArm.HOUR_1.value,
    DelayArm.HOUR_6.value,
    DelayArm.DAY_1.value,
    DelayArm.DAY_3.value,
    DelayArm.DAY_7.value,
]

FAILURE_CODES = [code.value for code in FailureCode]
BANKS = [bank.value for bank in Bank]
NETWORKS = [net.value for net in Network]

DAY_OF_MONTH_BUCKETS = ["early", "mid", "late"]

# ==============================================================================
# Day of Month Bucket Boundaries (Section 4.5 & User Instruction)
# - early: Days 1 to 5 (captures 1st-of-month salary credits & mandate processing)
# - mid:   Days 6 to 24 (standard operating cycle)
# - late:  Days 25 to 31 (month-end balance depletion & roll-over to next month)
# ==============================================================================
DAY_OF_MONTH_BOUNDARIES: Dict[str, tuple] = {
    "early": (1, 5),
    "mid": (6, 24),
    "late": (25, 31),
}

CUSTOMER_PRIOR_SUCCESS_BUCKETS = ["0", "1-3", "4+"]
CUSTOMER_PRIOR_FAILURES_BUCKETS = ["0", "1", "2+"]


# ==============================================================================
# Transaction Amount Distributions (Section 4.8 & User Instruction #2)
# ==============================================================================
# EXPLICIT FAILURE CODE TO AMOUNT DISTRIBUTION MAPPING:
# 1. 'issuer_timeout'    -> STANDARD (e.g., recurring SaaS/subscriptions, digital services)
# 2. 'generic_decline'   -> STANDARD (e.g., streaming, membership fees, standard utilities)
# 3. 'card_expired'      -> STANDARD (e.g., subscription accounts with lapsed cards)
# 4. 'insufficient_funds'-> HIGH-TICKET (e.g., EMIs, vehicle/personal loan installments, rent)
# 5. 'do_not_honor'      -> HIGH-TICKET (e.g., high-value charges triggering risk/fraud holds)
# ==============================================================================

AMOUNT_DISTRIBUTION_MAPPING: Dict[str, Literal["standard", "high_ticket"]] = {
    FailureCode.ISSUER_TIMEOUT.value: "standard",
    FailureCode.GENERIC_DECLINE.value: "standard",
    FailureCode.CARD_EXPIRED.value: "standard",
    FailureCode.INSUFFICIENT_FUNDS.value: "high_ticket",
    FailureCode.DO_NOT_HONOR.value: "high_ticket",
}

# Log-normal distribution parameters (log-mean mu, log-std sigma) in INR (₹)
AMOUNT_DISTRIBUTION_PARAMS = {
    "standard": {
        "mu": 7.3132,   # exp(7.3132) ≈ ₹1,500 median
        "sigma": 0.60,  # 80% range ≈ ₹690 to ₹3,260
        "min_amount": 100.0,
        "max_amount": 15000.0,
    },
    "high_ticket": {
        "mu": 8.5172,   # exp(8.5172) ≈ ₹5,000 median
        "sigma": 0.70,  # 80% range ≈ ₹2,000 to ₹12,500
        "min_amount": 500.0,
        "max_amount": 100000.0,
    },
}


# ==============================================================================
# Hidden Ground-Truth Base Recovery Curves P(recover | failure_code, bank, delay)
# Section 4.6 of Design Doc
# ==============================================================================

BASE_RECOVERY_PROBABILITIES: Dict[str, Dict[str, Dict[str, float]]] = {
    # 1. insufficient_funds: Recovers well later (1d/3d/7d), peaking near 3d/7d
    FailureCode.INSUFFICIENT_FUNDS.value: {
        Bank.BANK_A.value: {"1hr": 0.05, "6hr": 0.10, "1d": 0.25, "3d": 0.40, "7d": 0.35},
        Bank.BANK_B.value: {"1hr": 0.05, "6hr": 0.08, "1d": 0.15, "3d": 0.45, "7d": 0.30},  # Exact spec example
        Bank.BANK_C.value: {"1hr": 0.06, "6hr": 0.12, "1d": 0.22, "3d": 0.38, "7d": 0.32},
        Bank.BANK_D.value: {"1hr": 0.04, "6hr": 0.09, "1d": 0.20, "3d": 0.42, "7d": 0.33},
    },
    # 2. issuer_timeout: Recovers rapidly on quick retries (1hr, 6hr); decays if delayed
    FailureCode.ISSUER_TIMEOUT.value: {
        Bank.BANK_A.value: {"1hr": 0.65, "6hr": 0.55, "1d": 0.35, "3d": 0.20, "7d": 0.10},
        Bank.BANK_B.value: {"1hr": 0.60, "6hr": 0.50, "1d": 0.30, "3d": 0.18, "7d": 0.08},
        Bank.BANK_C.value: {"1hr": 0.78, "6hr": 0.68, "1d": 0.40, "3d": 0.22, "7d": 0.10},  # Bank C is timeout-prone
        Bank.BANK_D.value: {"1hr": 0.62, "6hr": 0.52, "1d": 0.32, "3d": 0.18, "7d": 0.08},
    },
    # 3. do_not_honor: Risk-based decline, baseline rarely recovers regardless of delay
    FailureCode.DO_NOT_HONOR.value: {
        Bank.BANK_A.value: {"1hr": 0.03, "6hr": 0.04, "1d": 0.05, "3d": 0.04, "7d": 0.02},
        Bank.BANK_B.value: {"1hr": 0.02, "6hr": 0.03, "1d": 0.04, "3d": 0.05, "7d": 0.03},
        Bank.BANK_C.value: {"1hr": 0.04, "6hr": 0.05, "1d": 0.05, "3d": 0.03, "7d": 0.02},
        Bank.BANK_D.value: {"1hr": 0.03, "6hr": 0.04, "1d": 0.05, "3d": 0.04, "7d": 0.02},  # Pre-day 20 baseline
    },
    # 4. card_expired: Never recovers via retry (0.0% strictly)
    FailureCode.CARD_EXPIRED.value: {
        Bank.BANK_A.value: {"1hr": 0.00, "6hr": 0.00, "1d": 0.00, "3d": 0.00, "7d": 0.00},
        Bank.BANK_B.value: {"1hr": 0.00, "6hr": 0.00, "1d": 0.00, "3d": 0.00, "7d": 0.00},
        Bank.BANK_C.value: {"1hr": 0.00, "6hr": 0.00, "1d": 0.00, "3d": 0.00, "7d": 0.00},
        Bank.BANK_D.value: {"1hr": 0.00, "6hr": 0.00, "1d": 0.00, "3d": 0.00, "7d": 0.00},
    },
    # 5. generic_decline: Moderate, fairly flat recovery across delays
    FailureCode.GENERIC_DECLINE.value: {
        Bank.BANK_A.value: {"1hr": 0.22, "6hr": 0.24, "1d": 0.25, "3d": 0.23, "7d": 0.20},
        Bank.BANK_B.value: {"1hr": 0.20, "6hr": 0.23, "1d": 0.25, "3d": 0.24, "7d": 0.21},
        Bank.BANK_C.value: {"1hr": 0.23, "6hr": 0.25, "1d": 0.26, "3d": 0.22, "7d": 0.19},
        Bank.BANK_D.value: {"1hr": 0.21, "6hr": 0.22, "1d": 0.24, "3d": 0.23, "7d": 0.20},
    },
}

# Bank D Drift: Starting at simulated day >= 20, Bank D loosens its do_not_honor policy
BANK_D_DRIFT_DAY = 20
BANK_D_DRIFT_PROBABILITIES: Dict[str, float] = {
    "1hr": 0.10,
    "6hr": 0.25,
    "1d": 0.52,
    "3d": 0.48,
    "7d": 0.25,
}


# ==============================================================================
# Modifiers on the Base Curve (Section 4.7 & User Instruction #1)
# ==============================================================================

# Network modifier: mild multiplicative adjustment
NETWORK_MODIFIERS: Dict[str, float] = {
    Network.VISA.value: 1.05,
    Network.MASTERCARD.value: 1.00,
    Network.RUPAY.value: 0.90,
}

# Customer history: prior success boost
CUSTOMER_SUCCESS_MODIFIERS: Dict[str, float] = {
    "0": 0.85,
    "1-3": 1.00,
    "4+": 1.15,
}

# Customer history: prior failures in current cycle penalty
# (Per user instruction #1: cycle fatigue is folded into this modifier)
CUSTOMER_FAILURE_CYCLE_MODIFIERS: Dict[str, float] = {
    "0": 1.00,
    "1": 0.85,
    "2+": 0.70,
}

# Default retry cost in ₹ per attempt (Section 5)
DEFAULT_RETRY_COST = 10.0
