"""
test_phase4_diagnostics.py
Unit tests for Phase 4A Strategy Intelligence Diagnostic Harness, provenance metadata, experimental isolation, dynamic runtime validation, and documentation consistency.
Verifies determinism, non-mutation of production config, provenance metadata structure, experimental directory safety, git fallback behavior, and cross-Python reproducibility.
"""

import pytest
import json
import sys
import shutil
import re
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


def test_historical_artifact_provenance():
    """Test A: Validates checked-in historical canonical metadata artifact schema without binding to active pytest Python version."""
    canonical_dir = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4_strategy_diagnostics"
    meta_path = canonical_dir / "phase4_run_metadata.json"
    summary_path = canonical_dir / "phase4_strategy_summary.json"

    assert summary_path.exists()
    assert meta_path.exists()

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["phase"] == "Phase 4A Strategy Intelligence Validation"
    assert meta["run_mode"] == "canonical"
    assert meta["diagnostic_script"] == "run_phase4_strategy_diagnostics.py"
    assert meta["transaction_count"] == CANONICAL_PHASE4_SAMPLE_SIZE
    assert meta["evaluation_sample_size"] == CANONICAL_PHASE4_SAMPLE_SIZE
    assert meta["sample_size"] == CANONICAL_PHASE4_SAMPLE_SIZE
    assert meta["configuration_fingerprint"] == "0580358a30ba"
    assert meta["primary_validation_environment"] == "Python 3.11.9"
    assert meta["intended_compatibility"] == "Python 3.9+"

    # Historical provenance must contain a valid version string format (e.g. 3.x.y)
    assert "python_version" in meta
    assert isinstance(meta["python_version"], str)
    assert re.match(r"^\d+\.\d+\.\d+", meta["python_version"]) is not None

    assert "git_commit" in meta
    assert meta["git_commit"] is not None
    assert "git_metadata_available" in meta


def test_dynamic_runtime_metadata_validation(tmp_path):
    """Test B: Generates fresh metadata in a temp directory and asserts that metadata dynamically captures active pytest Python interpreter."""
    run_phase4_diagnostics(eval_sample_size=100, output_dir=tmp_path)

    meta_file = tmp_path / "phase4_run_metadata.json"
    assert meta_file.exists()

    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    expected_py = sys.version.split()[0]
    assert meta["python_version"] == expected_py
    assert meta["primary_validation_environment"] == "Python 3.11.9"
    assert meta["intended_compatibility"] == "Python 3.9+"
    assert meta["transaction_count"] == 100
    assert meta["run_mode"] == "experimental"


def test_canonical_artifact_immutability_during_pytest(tmp_path):
    """Test C: Asserts that executing diagnostics with isolated output_dir does NOT alter checked-in canonical artifacts."""
    meta_path = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4_strategy_diagnostics" / "phase4_run_metadata.json"
    summary_path = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4_strategy_diagnostics" / "phase4_strategy_summary.json"

    with open(meta_path, "r", encoding="utf-8") as f:
        orig_meta_content = f.read()
    with open(summary_path, "r", encoding="utf-8") as f:
        orig_summary_content = f.read()

    # Execute diagnostic harness targeting temp directory
    run_phase4_diagnostics(eval_sample_size=5000, output_dir=tmp_path)

    # Assert canonical files in audit/ remain 100% identical
    with open(meta_path, "r", encoding="utf-8") as f:
        after_meta_content = f.read()
    with open(summary_path, "r", encoding="utf-8") as f:
        after_summary_content = f.read()

    assert orig_meta_content == after_meta_content
    assert orig_summary_content == after_summary_content


def test_experimental_isolation_safety(tmp_path):
    """Test D: Non-canonical sample size (20) writes to isolated tmp_path directory and DOES NOT overwrite canonical artifacts or leave source tree files."""
    canonical_dir = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4_strategy_diagnostics"
    canonical_meta = canonical_dir / "phase4_run_metadata.json"
    canonical_summary = canonical_dir / "phase4_strategy_summary.json"
    assert canonical_summary.exists()
    assert canonical_meta.exists()

    with open(canonical_summary, "r", encoding="utf-8") as f:
        orig_summary_content = f.read()
    with open(canonical_meta, "r", encoding="utf-8") as f:
        orig_meta_content = f.read()

    # Run non-canonical experimental run with sample size 20 targeting isolated tmp_path
    exp_out_dir = tmp_path / "experimental" / "sample_size_20"
    run_phase4_diagnostics(eval_sample_size=20, output_dir=exp_out_dir)

    # Verify experimental output exists in isolated tmp_path directory
    assert exp_out_dir.exists()
    exp_summary = exp_out_dir / "phase4_strategy_summary.json"
    exp_meta = exp_out_dir / "phase4_run_metadata.json"
    assert exp_summary.exists()
    assert exp_meta.exists()

    with open(exp_summary, "r", encoding="utf-8") as f:
        exp_data = json.load(f)

    assert exp_data["sample_size"] == 20
    assert exp_data["run_mode"] == "experimental"

    # Verify canonical summary & meta were NOT overwritten and remain byte-for-byte unchanged
    with open(canonical_summary, "r", encoding="utf-8") as f:
        after_summary_content = f.read()
    with open(canonical_meta, "r", encoding="utf-8") as f:
        after_meta_content = f.read()

    assert orig_summary_content == after_summary_content
    assert orig_meta_content == after_meta_content

    # Assert ValueError when trying to overwrite canonical directory with sample_size != 5000
    with pytest.raises(ValueError, match="strictly forbidden"):
        run_phase4_diagnostics(eval_sample_size=20, output_dir=canonical_dir)


def test_git_fallback_behavior():
    """Test E: Git fallback returns unavailable_in_source_archive and git_metadata_available == False when git fails."""
    commit_hash, git_avail = get_git_commit_info()
    assert commit_hash is not None
    assert isinstance(git_avail, bool)

    if not (PROJECT_ROOT / ".git").exists():
        assert commit_hash == "unavailable_in_source_archive"
        assert git_avail is False


def test_readme_and_report_discoverability():
    """Test F: README and canonical reports contain valid discoverability references."""
    readme_path = PROJECT_ROOT / "README.md"
    assert readme_path.exists()
    content = readme_path.read_text(encoding="utf-8")
    assert "run_phase4_strategy_diagnostics.py" in content
    assert "PHASE4_STRATEGY_INTELLIGENCE_REPORT.md" in content


def test_run_mode_describes_sample_configuration_not_output_destination(tmp_path):
    """Test G: Asserts that run_mode classifies the sample configuration (canonical = 5000) independently from output_dir destination."""
    canonical_dir = PROJECT_ROOT / "audit" / "evaluation_results" / "phase4_strategy_diagnostics"
    canonical_meta = canonical_dir / "phase4_run_metadata.json"
    assert canonical_meta.exists()

    with open(canonical_meta, "r", encoding="utf-8") as f:
        orig_meta_content = f.read()

    # Execute canonical sample configuration (5000 txs) redirected to isolated tmp_path
    run_phase4_diagnostics(eval_sample_size=CANONICAL_PHASE4_SAMPLE_SIZE, output_dir=tmp_path)

    # Verify artifacts were written to tmp_path
    tmp_meta = tmp_path / "phase4_run_metadata.json"
    tmp_summary = tmp_path / "phase4_strategy_summary.json"
    assert tmp_meta.exists()
    assert tmp_summary.exists()

    with open(tmp_meta, "r", encoding="utf-8") as f:
        meta_data = json.load(f)
    with open(tmp_summary, "r", encoding="utf-8") as f:
        summary_data = json.load(f)

    # Verify run_mode is "canonical" because sample size is 5000, even though output destination is tmp_path
    assert meta_data["run_mode"] == "canonical"
    assert summary_data["run_mode"] == "canonical"
    assert meta_data["sample_size"] == 5000

    # Verify checked-in canonical evidence directory was NOT modified
    with open(canonical_meta, "r", encoding="utf-8") as f:
        after_meta_content = f.read()

    assert orig_meta_content == after_meta_content

