"""
Bandit-Optimized Retry Scheduler
Razorpay AI Buildathon 2026 - Track 3 (AI Revenue Recovery)
"""

import sys
import types
from pathlib import Path

__version__ = "0.1.0"

# Register virtual package mapping for bandit_retry_scheduler if needed
_root = Path(__file__).resolve().parent
if "bandit_retry_scheduler" not in sys.modules:
    _mod = types.ModuleType("bandit_retry_scheduler")
    _mod.__path__ = [str(_root)]
    sys.modules["bandit_retry_scheduler"] = _mod
