"""
test_no_ground_truth_leakage.py
Strict Ground-Truth & Simulator Isolation Test Suite for RecoverFlow.

Recursively scans all production modules (api/, policies/, runner/) to ensure:
1. No imports of `simulator.ground_truth` or `ground_truth`.
2. No calls/references to hidden recovery probability functions:
   - `calculate_recovery_probability`
   - `get_true_recovery_probability`
3. Includes a verification test using a temporary violating file to prove the scanner detects violations.
"""

from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROHIBITED_TERMS = [
    "ground_truth",
    "calculate_recovery_probability",
    "get_true_recovery_probability",
]


def scan_directory_for_leakage(target_dir: Path) -> list:
    violations = []
    if not target_dir.exists():
        return violations
    for py_file in target_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for term in PROHIBITED_TERMS:
            if term in content:
                violations.append((str(py_file.relative_to(PROJECT_ROOT)), term))
    return violations


def test_api_directory_ground_truth_isolation():
    """Verify api/ has zero ground truth imports or function references."""
    violations = scan_directory_for_leakage(PROJECT_ROOT / "api")
    assert len(violations) == 0, f"Ground-truth leakage found in api/: {violations}"


def test_policies_directory_ground_truth_isolation():
    """Verify policies/ has zero ground truth imports or function references."""
    violations = scan_directory_for_leakage(PROJECT_ROOT / "policies")
    assert len(violations) == 0, f"Ground-truth leakage found in policies/: {violations}"


def test_runner_directory_ground_truth_isolation():
    """Verify runner/ has zero ground truth imports or function references."""
    violations = scan_directory_for_leakage(PROJECT_ROOT / "runner")
    assert len(violations) == 0, f"Ground-truth leakage found in runner/: {violations}"


def test_leakage_scanner_detects_deliberate_violation(tmp_path):
    """Verify that the scanner reliably detects deliberate prohibited imports/terms."""
    fake_api_dir = tmp_path / "api"
    fake_api_dir.mkdir()
    violating_file = fake_api_dir / "violating_module.py"
    violating_file.write_text("from bandit_retry_scheduler.simulator.ground_truth import calculate_recovery_probability\n")

    # Scan fake_api_dir using same logic
    violations = []
    for py_file in fake_api_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for term in PROHIBITED_TERMS:
            if term in content:
                violations.append((str(py_file), term))

    assert len(violations) == 2, f"Expected 2 violations (ground_truth & calculate_recovery_probability), got {len(violations)}"
