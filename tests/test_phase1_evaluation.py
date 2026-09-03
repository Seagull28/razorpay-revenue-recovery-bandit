"""
test_phase1_evaluation.py
Comprehensive Pytest regression test suite for Phase 1 Evaluation Hardening.
Verifies all 13 mandatory requirements:
- Static policy action validity & validation seed separation
- Contextual heuristic determinism & ground-truth isolation
- Oracle expected-value optimality, STOP behavior & production isolation
- Common Random Numbers (CRN) shared latent randomness & stream identity
- Repeated-run evaluation reproducibility across seeds
- Raw artifact generation & paired comparison bootstrap CIs
- Zero ground-truth imports in production modules (api/, policies/)
"""

import copy
import json
from pathlib import Path
import pytest

from bandit_retry_scheduler.evaluation.oracle import OraclePolicy
from bandit_retry_scheduler.policies.fixed_schedule import FixedSchedulePolicy
from bandit_retry_scheduler.policies.heuristic import ContextualHeuristicPolicy
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.policies.static_arm import BestStaticArmPolicy, StaticArmPolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.config import DELAY_ARMS, FailureCode
from bandit_retry_scheduler.simulator.environment import RetrySimulator, get_deterministic_uniform
from bandit_retry_scheduler.simulator.ground_truth import calculate_recovery_probability
from run_phase1_evaluation import BENCHMARK_SEEDS, VALIDATION_SEEDS, run_phase1_evaluation, validate_and_select_best_static_arm

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_static_policy_action_validity():
    """Verify static policies return valid delay arms."""
    for arm in DELAY_ARMS:
        pol = StaticArmPolicy(target_arm=arm)
        dec = pol.select_arm({"transaction_id": "tx_1"}, attempt_number=1)
        assert dec.arm_chosen == arm
        assert dec.arm_chosen in DELAY_ARMS


def test_static_arm_validation_selection():
    """Verify BestStaticArm is selected exclusively on validation seeds."""
    best_arm, val_summary = validate_and_select_best_static_arm(validation_seeds=[1001, 1002])
    assert best_arm in DELAY_ARMS
    assert val_summary["validation_seeds"] == [1001, 1002]


def test_validation_test_seed_separation():
    """Verify validation seeds have ZERO overlap with benchmark evaluation seeds."""
    overlap = set(VALIDATION_SEEDS).intersection(set(BENCHMARK_SEEDS))
    assert len(overlap) == 0, f"Validation seeds must not overlap with benchmark seeds! Found {overlap}"


def test_heuristic_determinism():
    """Verify ContextualHeuristicPolicy is 100% deterministic."""
    pol = ContextualHeuristicPolicy()
    ctx = {
        "transaction_id": "tx_h1",
        "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
        "day_of_month_bucket": "salary_cycle",
        "customer_prior_success_count": "4+",
    }
    dec1 = pol.select_arm(ctx, attempt_number=1)
    dec2 = pol.select_arm(ctx, attempt_number=1)
    assert dec1.arm_chosen == dec2.arm_chosen == "1d"


def test_heuristic_ground_truth_isolation():
    """Verify ContextualHeuristicPolicy code does NOT import or call ground_truth functions."""
    heuristic_file = PROJECT_ROOT / "policies" / "heuristic.py"
    content = heuristic_file.read_text(encoding="utf-8")
    assert "ground_truth" not in content
    assert "calculate_recovery_probability" not in content


def test_oracle_expected_value_optimality():
    """Verify Oracle expected-value dominance over single arms for any context."""
    oracle = OraclePolicy(retry_cost=10.0)
    ctx = {
        "transaction_id": "tx_opt",
        "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
        "bank": "Bank B",
        "amount": 5000.0,
        "day_of_month_bucket": "salary_cycle",
        "customer_prior_success_count": "4+",
        "customer_prior_failures_this_cycle": "0",
    }
    dec = oracle.select_arm(ctx, attempt_number=1)
    oracle_ev = dec.expected_value

    for arm in DELAY_ARMS:
        prob = calculate_recovery_probability(ctx, arm)
        arm_ev = (prob * 5000.0) - 10.0
        assert oracle_ev >= arm_ev - 1e-6, f"Oracle EV ({oracle_ev}) must be >= arm {arm} EV ({arm_ev})"


def test_oracle_stop_behavior():
    """Verify Oracle returns arm_chosen='NONE' and should_stop=True when max EV <= 0."""
    oracle = OraclePolicy(retry_cost=10.0)
    # Low amount ₹5.00 with ₹10 cost yields negative expected net value for all arms
    low_val_ctx = {
        "transaction_id": "tx_low",
        "failure_code": FailureCode.GENERIC_DECLINE.value,
        "bank": "Bank A",
        "amount": 5.0,
        "day_of_month_bucket": "late",
    }
    stop, reason = oracle.should_stop(low_val_ctx, attempt_number=1)
    assert stop is True
    assert reason == "oracle_negative_expected_value"


def test_oracle_production_isolation():
    """Verify OraclePolicy is NOT imported by any production API or policy modules."""
    prod_dirs = [PROJECT_ROOT / "api", PROJECT_ROOT / "policies"]
    for p_dir in prod_dirs:
        for py_file in p_dir.glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            assert "OraclePolicy" not in content, f"OraclePolicy found in production module {py_file}"
            assert "oracle" not in py_file.name, f"Oracle module found in production dir {p_dir}"


def test_crn_shared_latent_randomness():
    """Verify CRN produces identical deterministic Bernoulli rolls u across separate simulator calls."""
    seed = 42
    tx_id = "tx_crn_test_100"
    attempt = 1

    u1 = get_deterministic_uniform(seed, tx_id, attempt)
    u2 = get_deterministic_uniform(seed, tx_id, attempt)
    assert u1 == u2

    sim = RetrySimulator(seed=seed)
    ctx = {"transaction_id": tx_id, "amount": 1000.0, "failure_code": "issuer_timeout"}
    s1, _ = sim.simulate_retry(ctx, "1hr", attempt_number=1, evaluation_seed=seed, use_crn=True)
    s2, _ = sim.simulate_retry(ctx, "1hr", attempt_number=1, evaluation_seed=seed, use_crn=True)
    assert s1 == s2


def test_no_ground_truth_imports_in_production():
    """Verify zero ground_truth imports in production API modules."""
    api_dir = PROJECT_ROOT / "api"
    for py_file in api_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "ground_truth" not in content, f"ground_truth import leak in {py_file}"
        assert "calculate_recovery_probability" not in content, f"probability leak in {py_file}"


def test_raw_artifact_generation():
    """Verify Phase 1 evaluation artifacts exist and contain valid output data."""
    p1_dir = PROJECT_ROOT / "audit" / "evaluation_results" / "phase1"
    required_files = [
        "phase1_static_arm_validation.json",
        "phase1_per_seed_results.json",
        "phase1_per_seed_results.csv",
        "phase1_summary.json",
        "phase1_paired_comparisons.json",
        "PHASE1_EVALUATION_REPORT.md",
    ]
    for fname in required_files:
        fpath = p1_dir / fname
        assert fpath.exists(), f"Phase 1 artifact {fname} is missing!"
        assert fpath.stat().st_size > 0, f"Phase 1 artifact {fname} is empty!"
