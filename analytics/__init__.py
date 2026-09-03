"""
RecoverFlow Analytics Package.
Provides aggregate merchant insights and recovery opportunity scoring.
"""

from bandit_retry_scheduler.analytics.recovery_insights import (
    generate_merchant_recovery_insights,
    calculate_opportunity_score,
)

__all__ = [
    "generate_merchant_recovery_insights",
    "calculate_opportunity_score",
]
