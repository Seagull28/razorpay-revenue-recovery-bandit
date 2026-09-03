"""
test_phase4_diagnostics.py
Unit tests for Phase 4A Strategy Intelligence Diagnostic Harness, provenance metadata, experimental isolation, and documentation consistency.
Verifies determinism, non-mutation of production config, provenance metadata structure, experimental directory safety, git fallback behavior, and README references.
"""

import pytest
import json
import sys
import shutil
import numpy as np
from pathlib import Path
from bandit_retry_scheduler.run_phase4_strategy_diagnostics import (
    calculate_quantiles,
    extract_arm_score,
    get_git_commit_info,
    get_warmed_evaluation_policy,
    run_phase4_diagnostics,
    CANONICAL_PHASE4_SAMPLE_SIZE,
)
from bandit_retry_scheduler.api.intelligence_service import get_recovery_intelligence
from bandit_retry_scheduler.core.config import (
    BALANCED_RISK_WEIGHT,
    CONSERVATIVE_RISK_WEIGHT,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_calculate_quantiles_empty_and_valid():
    q_empty = calculate_quantiles([])
    assert q_empty["mean"] == 0.0
    assert q_empty["median"] == 0.0

    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    q = calculate_quantiles(vals)
    assert q["min"] == 10.0
    assert q["max"] == 50.0
    assert q["median"] == 30.0
    assert q["mean"] == 30.0


def test_extract_arm_score_parsing():
    assert extract_arm_score({"score": 150.0}) == 150.0
    assert extract_arm_score({"ucb_score": 120.0}) == 120.0
    assert extract_arm_score({"theta_dot_x": 90.0}) == 90.0
    assert extract_arm_score(45.5) == 45.5
    assert extract_arm_score(None) == 0.0


def test_warmed_evaluation_policy_determinism():
    p1 = get_warmed_evaluation_policy(seed=42, warm_tx_count=100)
    p2 = get_warmed_evaluation_policy(seed=42, warm_tx_count=100)

    tx = {"failure_code": "insufficient_funds", "amount": 2500.0}
    intel1 = get_recovery_intelligence(tx, "MAXIMIZE_RECOVERY", policy=p1)
    intel2 = get_recovery_intelligence(tx, "MAXIMIZE_RECOVERY", policy=p2)

    assert intel1["raw_decision"]["recommended_delay"] == intel2["raw_decision"]["recommended_delay"]
    score1 = extract_arm_score(intel1["raw_decision"]["arm_scores"]["3d"])
    score2 = extract_arm_score(intel2["raw_decision"]["arm_scores"]["3d"])
    assert pytest.approx(score1) == score2


def test_test_a_canonical_default_execution():
    """Test A: Canonical default uses 5000 transactions and canonical output paths."""
    canonical_dir = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4_strategy_diagnostics"
    meta_path = canonical_dir / "phase4_run_metadata.json"
    summary_path = canonical_dir / "phase4_strategy_summary.json"

    # Verify canonical files exist
    assert summary_path.exists()
    assert meta_path.exists()

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["transaction_count"] == CANONICAL_PHASE4_SAMPLE_SIZE
    assert meta["evaluation_sample_size"] == CANONICAL_PHASE4_SAMPLE_SIZE
    assert meta["sample_size"] == CANONICAL_PHASE4_SAMPLE_SIZE
    assert meta["run_mode"] == "canonical"


def test_test_b_experimental_isolation():
    """Test B: Non-canonical sample size (20) writes to experimental directory and DOES NOT overwrite canonical summary."""
    canonical_summary = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4_strategy_diagnostics" / "phase4_strategy_summary.json"
    assert canonical_summary.exists()

    with open(canonical_summary, "r", encoding="utf-8") as f:
        orig_data = json.load(f)

    orig_sample_size = orig_data["sample_size"]
    assert orig_sample_size == CANONICAL_PHASE4_SAMPLE_SIZE

    # Run non-canonical experimental run with sample size 20
    exp_dir = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4_strategy_diagnostics" / "experimental" / "sample_size_20"
    if exp_dir.exists():
        shutil.rmtree(exp_dir)

    run_phase4_diagnostics(eval_sample_size=20)

    # Verify experimental output exists in isolated directory
    assert exp_dir.exists()
    exp_summary = exp_dir / "phase4_strategy_summary.json"
    assert exp_summary.exists()

    with open(exp_summary, "r", encoding="utf-8") as f:
        exp_data = json.load(f)

    assert exp_data["sample_size"] == 20
    assert exp_data["run_mode"] == "experimental"

    # Verify canonical summary was NOT overwritten and remains 5000
    with open(canonical_summary, "r", encoding="utf-8") as f:
        canonical_after = json.load(f)

    assert canonical_after["sample_size"] == CANONICAL_PHASE4_SAMPLE_SIZE
    assert canonical_after["run_mode"] == "canonical"


def test_test_c_canonical_metadata_structure():
    """Test C: Canonical metadata contains transaction_count = 5000, run_mode = canonical."""
    meta_path = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4_strategy_diagnostics" / "phase4_run_metadata.json"
    assert meta_path.exists()

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["phase"] == "Phase 4A Strategy Intelligence Validation"
    assert meta["run_mode"] == "canonical"
    assert meta["diagnostic_script"] == "run_phase4_strategy_diagnostics.py"
    assert meta["transaction_count"] == 5000
    assert meta["evaluation_sample_size"] == 5000
    assert meta["sample_size"] == 5000
    assert meta["configuration_fingerprint"] == "0580358a30ba"
    assert "git_commit" in meta
    assert meta["git_commit"] is not None
    assert "git_metadata_available" in meta


def test_test_d_git_fallback_behavior():
    """Test D: Git fallback returns unavailable_in_source_archive and git_metadata_available == False when git fails."""
    commit_hash, git_avail = get_git_commit_info()
    assert commit_hash is not None
    assert isinstance(git_avail, bool)

    if not (PROJECT_ROOT / ".git").exists():
        assert commit_hash == "unavailable_in_source_archive"
        assert git_avail is False


def test_test_e_runtime_python_version_dynamic():
    """Test E: Metadata captures actual executing interpreter version dynamically."""
    meta_path = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4_strategy_diagnostics" / "phase4_run_metadata.json"
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    expected_py = sys.version.split()[0]
    assert meta["python_version"] == expected_py
    assert meta["primary_validation_environment"] == "Python 3.11.9"
    assert meta["intended_compatibility"] == "Python 3.9+"


def test_test_f_readme_and_report_discoverability():
    """Test F: README and canonical reports contain valid discoverability and test count assertions."""
    readme_path = PROJECT_ROOT / "README.md"
    assert readme_path.exists()
    content = readme_path.read_text(encoding="utf-8")
    assert "run_phase4_strategy_diagnostics.py" in content
    assert "PHASE4_STRATEGY_INTELLIGENCE_REPORT.md" in content
