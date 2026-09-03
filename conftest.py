"""
conftest.py
Pytest configuration and automatic root package path registration for RecoverFlow.
Ensures bandit_retry_scheduler modules resolve natively during test collection
regardless of parent directory naming or installation status.
"""

import sys
import types
from pathlib import Path

# Register root directory and parent on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

# Register virtual package mapping for bandit_retry_scheduler if not present
if "bandit_retry_scheduler" not in sys.modules:
    mod = types.ModuleType("bandit_retry_scheduler")
    mod.__path__ = [str(PROJECT_ROOT)]
    sys.modules["bandit_retry_scheduler"] = mod
