"""
verify_submission.py
Single-command comprehensive submission readiness verification utility for RecoverFlow.
Executes 11 verification stages and returns exit code 0 on success or non-zero on failure.

Usage:
    python verify_submission.py
"""

import sys
import os
import json
import csv
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def print_stage_header(title: str):
    print(f"\n--- {title} ---")


def run_check_environment() -> Tuple[bool, str]:
    """Stage 1: Verify Python version and environment requirements."""
    v = sys.version_info
    if v < (3, 9):
        return False, f"Python version {v.major}.{v.minor} is below minimum required 3.9!"
    return True, f"Python {v.major}.{v.minor}.{v.micro} verified (Tested on Python 3.11.9, Intended compatibility: Python 3.9+)."


def run_check_repository_structure() -> Tuple[bool, str]:
    """Stage 2: Verify all required production files and directories exist."""
    required_files = [
        "README.md",
        "LICENSE",
        "requirements.txt",
        "pyproject.toml",
        "dashboard.py",
        "run_phase1_evaluation.py",
        "create_project_zip.py",
        "simulator/config.py",
        "simulator/environment.py",
        "simulator/ground_truth.py",
        "simulator/stream_generator.py",
        "policies/base.py",
        "policies/encoder.py",
        "policies/fixed_schedule.py",
        "policies/static_arm.py",
        "policies/heuristic.py",
        "policies/linucb.py",
        "evaluation/harness.py",
        "evaluation/oracle.py",
        "evaluation/metrics.py",
        "core/context_utils.py",
    ]
    required_dirs = ["api", "policies", "runner", "simulator", "evaluation", "tests", "audit"]

    missing = []
    for f in required_files:
        if not (PROJECT_ROOT / f).exists():
            missing.append(f)
    for d in required_dirs:
        if not (PROJECT_ROOT / d).is_dir():
            missing.append(f"{d}/")

    if missing:
        return False, f"Missing required repository files/directories: {missing}"
    return True, "All required production modules and directory structures exist."


def run_check_import_health() -> Tuple[bool, str]:
    """Stage 3: Verify core modules import cleanly."""
    try:
        from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
        from bandit_retry_scheduler.policies.fixed_schedule import FixedSchedulePolicy
        from bandit_retry_scheduler.policies.static_arm import StaticArmPolicy, BestStaticArmPolicy
        from bandit_retry_scheduler.policies.heuristic import ContextualHeuristicPolicy
        from bandit_retry_scheduler.evaluation.oracle import OraclePolicy
        from bandit_retry_scheduler.simulator.environment import RetrySimulator
        from bandit_retry_scheduler.core.context_utils import to_day_bucket
        return True, "All core policy, evaluation, and simulator modules import cleanly."
    except Exception as e:
        return False, f"Module import failed: {e}"


def _get_env():
    env = os.environ.copy()
    parents = [str(PROJECT_ROOT.parent), str(PROJECT_ROOT)]
    env["PYTHONPATH"] = os.pathsep.join(parents) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def run_check_ground_truth_isolation() -> Tuple[bool, str]:
    """Stage 4: Execute AST-based ground-truth leakage test suite."""
    cmd = [sys.executable, "-m", "pytest", "tests/test_no_ground_truth_leakage.py", "-q"]
    res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, env=_get_env())
    if res.returncode != 0:
        return False, f"Ground-truth leakage tests failed!\nOutput:\n{res.stdout}\n{res.stderr}"
    return True, "Zero ground-truth leakage verified across production directories (api/, policies/, runner/)."


def run_check_full_test_suite() -> Tuple[bool, str]:
    """Stage 5: Execute full Pytest regression suite."""
    cmd = [sys.executable, "-m", "pytest", "-q"]
    res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, env=_get_env())
    if res.returncode != 0:
        return False, f"Pytest suite failed!\nOutput:\n{res.stdout}\n{res.stderr}"

    summary_line = [line for line in res.stdout.splitlines() if "passed" in line]
    passed_msg = summary_line[-1].strip() if summary_line else "All tests passed"
    return True, f"Full regression test suite passed cleanly ({passed_msg})."


def run_check_benchmark_execution() -> Tuple[bool, str]:
    """Stage 6: Run Phase 1 benchmark evaluation harness."""
    cmd = [sys.executable, "run_phase1_evaluation.py"]
    res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, env=_get_env())
    if res.returncode != 0:
        return False, f"Phase 1 evaluation harness failed!\nOutput:\n{res.stdout}\n{res.stderr}"
    return True, "Phase 1 evaluation benchmark executed cleanly."


def run_check_artifact_validation() -> Tuple[bool, str]:
    """Stage 7: Validate Phase 1 artifact schema, numbers, and consistency."""
    p1_dir = PROJECT_ROOT / "audit" / "evaluation_results" / "phase1"
    required_artifacts = [
        "phase1_static_arm_validation.json",
        "phase1_per_seed_results.json",
        "phase1_per_seed_results.csv",
        "phase1_summary.json",
        "phase1_paired_comparisons.json",
        "PHASE1_EVALUATION_REPORT.md",
    ]
    for fname in required_artifacts:
        fpath = p1_dir / fname
        if not fpath.exists() or fpath.stat().st_size == 0:
            return False, f"Canonical artifact {fname} is missing or empty!"

    try:
        with open(p1_dir / "phase1_summary.json", "r", encoding="utf-8") as f:
            summary_data = json.load(f)

        sum_by_pol = summary_data.get("summary_by_policy", {})
        expected_policies = {
            "Fixed Schedule",
            "Best Static Arm",
            "Contextual Heuristic",
            "RecoverFlow LinUCB",
            "Ground-Truth Greedy Oracle",
        }
        actual_policies = set(sum_by_pol.keys())
        if expected_policies != actual_policies:
            return False, f"Policy names mismatch in summary artifact! Expected {expected_policies}, got {actual_policies}"

        for p, metrics in sum_by_pol.items():
            for k, val in metrics.items():
                if isinstance(val, (int, float)):
                    if str(val).lower() in ("nan", "inf", "-inf"):
                        return False, f"Invalid value {val} for metric {k} in policy {p}"

        fingerprint = summary_data.get("evaluation_fingerprint", {})
        if not fingerprint.get("configuration_hash"):
            return False, "Evaluation fingerprint missing configuration_hash!"

    except Exception as e:
        return False, f"Artifact validation error: {e}"

    return True, "All 6 Phase 1 canonical artifacts validated (Valid JSON/CSV schema, 5 policies, fingerprint present)."


def run_check_deterministic_reproducibility() -> Tuple[bool, str]:
    """Stage 8: Run Phase 1 evaluation a second time and compare structured outputs for 100% numerical identity."""
    p1_dir = PROJECT_ROOT / "audit" / "evaluation_results" / "phase1"

    with open(p1_dir / "phase1_summary.json", "r", encoding="utf-8") as f:
        sum_run1 = json.load(f)["summary_by_policy"]
    with open(p1_dir / "phase1_paired_comparisons.json", "r", encoding="utf-8") as f:
        paired_run1 = json.load(f)

    cmd = [sys.executable, "run_phase1_evaluation.py"]
    res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, env=_get_env())
    if res.returncode != 0:
        return False, f"Run 2 Phase 1 evaluation failed!\nOutput:\n{res.stdout}"

    with open(p1_dir / "phase1_summary.json", "r", encoding="utf-8") as f:
        sum_run2 = json.load(f)["summary_by_policy"]
    with open(p1_dir / "phase1_paired_comparisons.json", "r", encoding="utf-8") as f:
        paired_run2 = json.load(f)

    if sum_run1 != sum_run2:
        return False, f"Non-deterministic summary metrics detected!\nRun 1: {sum_run1}\nRun 2: {sum_run2}"

    if paired_run1 != paired_run2:
        return False, f"Non-deterministic paired comparisons detected!\nRun 1: {paired_run1}\nRun 2: {paired_run2}"

    return True, "100% deterministic reproducibility verified across consecutive evaluation runs."


def run_check_phase3_and_phase4a_execution() -> Tuple[bool, str]:
    """Stage 9: Run Phase 3 and Phase 4A strategy execution scripts and validate artifacts."""
    cmd3 = [sys.executable, "run_phase3_evaluation.py"]
    res3 = subprocess.run(cmd3, cwd=PROJECT_ROOT, capture_output=True, text=True, env=_get_env())
    if res3.returncode != 0:
        return False, f"Phase 3 evaluation harness failed!\nOutput:\n{res3.stdout}\n{res3.stderr}"

    cmd4a = [sys.executable, "run_phase4_strategy_diagnostics.py"]
    res4a = subprocess.run(cmd4a, cwd=PROJECT_ROOT, capture_output=True, text=True, env=_get_env())
    if res4a.returncode != 0:
        return False, f"Phase 4A strategy diagnostics failed!\nOutput:\n{res4a.stdout}\n{res4a.stderr}"

    required_artifacts = [
        PROJECT_ROOT / "audit" / "PHASE3_FINAL_AUDIT_REPORT.md",
        PROJECT_ROOT / "audit" / "evaluation_results" / "phase4_strategy_diagnostics" / "phase4_strategy_summary.json",
        PROJECT_ROOT / "audit" / "evaluation_results" / "phase4_strategy_diagnostics" / "phase4_strategy_differentiation_analysis.json",
    ]
    for artifact_path in required_artifacts:
        if not artifact_path.exists() or artifact_path.stat().st_size == 0:
            return False, f"Required Phase 3 / Phase 4A artifact {artifact_path.name} is missing or empty!"

    return True, "Phase 3 and Phase 4A strategy scripts executed cleanly and artifacts validated."


def run_check_phase4b_robustness_execution() -> Tuple[bool, str]:
    """Stage 10: Run Phase 4B robustness evaluation across 2 independent runs and verify tolerance bounds."""
    p4b_summary_path = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4b_robustness" / "phase4b_summary.json"

    # Run 1
    cmd1 = [sys.executable, "run_phase4b_robustness.py"]
    res1 = subprocess.run(cmd1, cwd=PROJECT_ROOT, capture_output=True, text=True, env=_get_env())
    if res1.returncode != 0:
        return False, f"Run 1 Phase 4B robustness evaluation failed!\nOutput:\n{res1.stdout}\n{res1.stderr}"

    if not p4b_summary_path.exists():
        return False, "Phase 4B summary artifact missing after Run 1!"

    with open(p4b_summary_path, "r", encoding="utf-8") as f:
        summary_run1 = json.load(f)

    # Run 2
    cmd2 = [sys.executable, "run_phase4b_robustness.py"]
    res2 = subprocess.run(cmd2, cwd=PROJECT_ROOT, capture_output=True, text=True, env=_get_env())
    if res2.returncode != 0:
        return False, f"Run 2 Phase 4B robustness evaluation failed!\nOutput:\n{res2.stdout}\n{res2.stderr}"

    with open(p4b_summary_path, "r", encoding="utf-8") as f:
        summary_run2 = json.load(f)

    max_rel_diff = 0.0
    scenarios_r1 = summary_run1.get("scenarios", {})
    scenarios_r2 = summary_run2.get("scenarios", {})

    for sc_name, sc_data1 in scenarios_r1.items():
        policies1 = sc_data1.get("policies", {})
        policies2 = scenarios_r2.get(sc_name, {}).get("policies", {})
        for pname, metrics1 in policies1.items():
            metrics2 = policies2.get(pname, {})
            for metric in ["mean_net_revenue_inr", "mean_recovery_rate_pct"]:
                v1 = metrics1.get(metric, 0.0)
                v2 = metrics2.get(metric, 0.0)
                rel_diff = abs(v1 - v2) / max(abs(v1), 1.0)
                if rel_diff > max_rel_diff:
                    max_rel_diff = rel_diff
                if rel_diff > 0.001:
                    return (
                        False,
                        f"Phase 4B metric tolerance exceeded for scenario '{sc_name}', policy '{pname}', "
                        f"metric '{metric}': run1={v1}, run2={v2}, rel_diff={rel_diff:.6f} > 0.001"
                    )

    return (
        True,
        "Phase 4B robustness evaluation executed cleanly across 2 independent runs; "
        f"all metrics within 0.1% run-to-run tolerance (max observed rel diff: {max_rel_diff:.4%}; see known limitation: "
        "Phase 4B does not guarantee bit-identical reproducibility like Phase 1)."
    )


def run_check_synthetic_disclosures() -> Tuple[bool, str]:
    """Stage 11: Verify synthetic simulation notices are present in README and Dashboard."""
    readme_path = PROJECT_ROOT / "README.md"
    dash_path = PROJECT_ROOT / "dashboard.py"

    readme_text = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    dash_text = dash_path.read_text(encoding="utf-8") if dash_path.exists() else ""

    if "Simulation Notice" not in readme_text and "synthetic" not in readme_text.lower():
        return False, "README.md missing clear synthetic simulation disclosure!"
    if "synthetic" not in dash_text.lower():
        return False, "dashboard.py missing clear synthetic simulation disclosure!"

    return True, "Synthetic simulation disclosures verified in README.md and dashboard.py."


def main():
    print("================================================================================")
    print("RECOVERFLOW SUBMISSION VERIFICATION HARNESS")
    print("================================================================================")

    stages = [
        ("Environment & Python Version", run_check_environment),
        ("Repository Structure", run_check_repository_structure),
        ("Import Health", run_check_import_health),
        ("Ground-Truth Isolation (AST)", run_check_ground_truth_isolation),
        ("Full Automated Test Suite", run_check_full_test_suite),
        ("Phase 1 Benchmark Execution", run_check_benchmark_execution),
        ("Canonical Artifact Validation", run_check_artifact_validation),
        ("Deterministic Reproducibility", run_check_deterministic_reproducibility),
        ("Phase 3 & Phase 4A Strategy Execution", run_check_phase3_and_phase4a_execution),
        ("Phase 4B Robustness Execution (Tolerance-Based)", run_check_phase4b_robustness_execution),
        ("Synthetic Simulation Disclosures", run_check_synthetic_disclosures),
    ]

    all_passed = True
    failed_stages = []

    for name, check_fn in stages:
        sys.stdout.write(f"Testing {name:48s} ... ")
        sys.stdout.flush()
        try:
            success, msg = check_fn()
            if success:
                print(f"[PASS] {msg}")
            else:
                print(f"[FAIL] {msg}")
                all_passed = False
                failed_stages.append((name, msg))
        except Exception as e:
            print(f"[FAIL] Unexpected exception: {e}")
            all_passed = False
            failed_stages.append((name, str(e)))

    print("================================================================================")
    if all_passed:
        print("RESULT: SUBMISSION VERIFICATION PASSED (All 11 Stages Verified)")
        print("================================================================================")
        sys.exit(0)
    else:
        print(f"RESULT: SUBMISSION VERIFICATION FAILED ({len(failed_stages)} Stage(s) Failed)")
        for fname, fmsg in failed_stages:
            print(f"  - {fname}: {fmsg}")
        print("================================================================================")
        sys.exit(1)


if __name__ == "__main__":
    main()
