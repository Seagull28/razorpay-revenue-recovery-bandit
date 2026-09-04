"""
context_utils.py
Neutral context transformation utilities for RecoverFlow.
Contains generic, deterministic context feature bucket transformers.
Has ZERO top-level dependency on simulator ground truth or config.
"""

from typing import Union


def to_success_bucket(val: Union[int, str]) -> str:
    """Converts a prior success count (integer or string) to a standard bucket ('0', '1-3', '4+')."""
    if isinstance(val, str):
        if val in ["0", "1-3", "4+"]:
            return val
        try:
            val = int(val)
        except ValueError:
            return "1-3"
    if val <= 0:
        return "0"
    elif val <= 3:
        return "1-3"
    else:
        return "4+"


def to_failure_bucket(val: Union[int, str]) -> str:
    """Converts a prior failures count (integer or string) to a standard bucket ('0', '1', '2+')."""
    if isinstance(val, str):
        if val in ["0", "1", "2+"]:
            return val
        try:
            val = int(val)
        except ValueError:
            return "0"
    if val <= 0:
        return "0"
    elif val == 1:
        return "1"
    else:
        return "2+"


def to_day_bucket(day_of_month: Union[int, str]) -> str:
    """
    Converts a day of the month (1-31) to ('early', 'mid', 'late')
    using DAY_OF_MONTH_BOUNDARIES from config.py.
    """
    from bandit_retry_scheduler.simulator.config import DAY_OF_MONTH_BOUNDARIES

    if isinstance(day_of_month, str):
        if day_of_month in DAY_OF_MONTH_BOUNDARIES:
            return day_of_month
        try:
            day_of_month = int(day_of_month)
        except ValueError:
            return "mid"

    for bucket_name, (start_day, end_day) in DAY_OF_MONTH_BOUNDARIES.items():
        if start_day <= day_of_month <= end_day:
            return bucket_name
    return "mid"
