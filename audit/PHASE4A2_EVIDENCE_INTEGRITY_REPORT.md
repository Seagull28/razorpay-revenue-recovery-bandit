# 🛡️ RECOVERFLOW PHASE 4A.2 EVIDENCE INTEGRITY & REPRODUCIBILITY HARDENING REPORT

> **Canonical Artifact Protection, Provenance Standardization, Experimental Isolation, and Forensic Documentation Reconciliation**

---

## 1. Baseline State

Execution baseline prior to Phase 4A.2 hardening pass:

```text
Git Branch          : main (Commit 28afd3d)
Git Status          : On branch main, working tree clean
Pytest Baseline     : 101 collected / 101 passed in 19.34s
Phase 1 Hash        : 0580358a30ba (100% Intact)
Best Static Arm     : 3d (100% Intact)
Locked Core Files   : UNTOUCHED (policies/linucb.py, policies/encoder.py, simulator/ground_truth.py, run_phase1_evaluation.py, core/config.py, core/risk.py, core/strategy.py)
```

---

## 2. Issue Summary & Resolution Overview

| Issue ID | Identified Vulnerability / Ambiguity | Implemented Phase 4A.2 Resolution |
| :--- | :--- | :--- |
| **Issue 1** | **20 vs. 5,000 Transaction Discrepancy** | Canonical evaluation enforced strictly at `CANONICAL_PHASE4_SAMPLE_SIZE = 5000`. Regenerated all 9 canonical Phase 4 artifacts. |
| **Issue 2** | **Experimental Overwrite Risk** | Non-canonical runs (e.g. `--sample-size 20`) are strictly routed to `audit/evaluation_results/phase4_strategy_diagnostics/experimental/sample_size_<N>/`. Overwriting canonical artifact path raises `ValueError`. |
| **Issue 3** | **Null Git Provenance (`git_commit: null`)** | Implemented `get_git_commit_info()`. When `.git` is available, returns 7-char commit hash; when `.git` is absent (clean-room ZIP extraction), returns `"unavailable_in_source_archive"` with `"git_metadata_available": false`. Never returns `null`. |
| **Issue 4** | **Python Environment Ambiguity** | Separated `"primary_validation_environment": "Python 3.11.9"`, `"intended_compatibility": "Python 3.9+"`, and `"python_version"` (captured dynamically via `sys.version`). |
| **Issue 5** | **Stale Test Count Ambiguity** | Conducted repository-wide forensic scan. Classified all test count references (Historical Phase 3: `93 passed`, Phase 4A initial: `97 passed`, Phase 4A.1 status: `101 passed`, Phase 4A.2 final status: `103 passed`). |
| **Issue 6** | **Phase 4 Report & Artifact Discrepancy** | All reported metrics in `PHASE4_STRATEGY_INTELLIGENCE_REPORT.md` and `README.md` trace programmatically to the regenerated 5,000-transaction canonical artifacts. |

---

## 3. Canonical Evaluation Contract

- **Canonical Sample Size**: `CANONICAL_PHASE4_SAMPLE_SIZE = 5000`
- **Canonical Command**: `python run_phase4_strategy_diagnostics.py`
- **Canonical Output Directory**: `audit/evaluation_results/phase4_strategy_diagnostics/`
- **Canonical Mode Indicator**: `"run_mode": "canonical"`

---

## 4. Experimental Isolation Contract

```text
[EXECUTION INPUT]
        │
        ├── Sample Size == 5000 (Default)
        │   └── Mode: CANONICAL
        │   └── Target: audit/evaluation_results/phase4_strategy_diagnostics/
        │
        └── Sample Size != 5000 (e.g. --sample-size 20)
            └── Mode: EXPERIMENTAL
            └── Target: audit/evaluation_results/phase4_strategy_diagnostics/experimental/sample_size_<N>/
            └── Safety Rule: Writing to canonical directory raises ValueError!
```

---

## 5. Canonical Artifact Verification

Regenerated canonical 5,000-transaction artifacts verified programmatically:

```json
{
  "sample_size": 5000,
  "evaluation_sample_size": 5000,
  "transaction_count": 5000,
  "run_mode": "canonical",
  "confidence_stats": {
    "min": 0.0208,
    "mean": 0.9405,
    "median": 1.0
  },
  "ambiguity_tier_distribution": {
    "STRONGLY_DOMINANT": { "count": 4708, "percentage": 94.16 },
    "CLEAR_WINNER": { "count": 184, "percentage": 3.68, "disagreement_rate_pct": 26.09 },
    "MODERATELY_SEPARATED": { "count": 64, "percentage": 1.28, "balanced_override_rate_pct": 43.75 }
  },
  "ambiguous_subset_analysis": {
    "full_dataset": { "count": 5000, "disagreement_rate_pct": 2.32 },
    "lowest_10pct_confidence_subset": { "count": 505, "disagreement_rate_pct": 22.97, "conservative_override_rate_pct": 35.84 }
  }
}
```

---

## 6. Provenance Verification

- **Git Commit Hash**: Captured dynamically (`commit_hash` when `.git` exists, `"unavailable_in_source_archive"` when `.git` is absent).
- **Git Metadata Flag**: `git_metadata_available` (`True` when `.git` exists, `False` when absent).
- **Runtime Python**: Captured dynamically (`sys.version.split()[0]`).
- **Validation Target**: `Python 3.11.9` (Primary environment).
- **Compatibility Target**: `Python 3.9+`.

---

## 7. Documentation Reconciliation & Test Count Audit

Repository-wide scan results for historical test counts:

| Milestone / Snapshot | Test Count | Classification | Context / Location |
| :--- | :---: | :--- | :--- |
| **Phase 1 Baseline** | 42 passed | `HISTORICAL` | Phase 1 benchmark summary & evaluation reports |
| **Phase 3 Final Baseline** | 93 passed | `HISTORICAL` | Explicitly labeled Phase 3 final snapshot in `PHASE3_FINAL_AUDIT_REPORT.md` |
| **Phase 4A Initial Status** | 97 passed | `HISTORICAL` | Initial Phase 4A strategy diagnostic harness commit |
| **Phase 4A.1 Status** | 101 passed | `HISTORICAL` | Added `test_dashboard_smoke.py` suite |
| **Phase 4A.2 Final Status** | **103 passed** | `CURRENT` | Final post-hardening test suite (`tests/test_phase4_diagnostics.py` Tests A-F added) |

---

## 8. Locked Core Files Verification

- `policies/linucb.py`: **UNTOUCHED (100% Intact)**
- `policies/encoder.py`: **UNTOUCHED (100% Intact)**
- `simulator/ground_truth.py`: **UNTOUCHED (100% Intact)**
- `run_phase1_evaluation.py`: **UNTOUCHED (100% Intact)**
- `core/config.py`: **UNTOUCHED (100% Intact)**
- `core/risk.py`: **UNTOUCHED (100% Intact)**
- `core/strategy.py`: **UNTOUCHED (100% Intact)**

---

## 9. Phase 1 Regression Verification

Executed `python run_phase1_evaluation.py`:

- **Configuration Fingerprint Hash**: `0580358a30ba` (**100% IDENTICAL**)
- **Selected Best Static Arm**: `3d` (**100% IDENTICAL**)
- **Fixed Schedule Baseline Net**: `INR 8,765,870.96` (**100% IDENTICAL**)
- **Best Static Arm Net**: `INR 9,273,734.06` (**100% IDENTICAL**)
- **RecoverFlow LinUCB Net**: `INR 9,486,147.13` (**100% IDENTICAL**)
- **Ground-Truth Oracle Net**: `INR 9,853,890.23` (**100% IDENTICAL**)

---

## 10. Test Results

Executed `python -m pytest --collect-only -q` and `python -m pytest -q`:

- **Collected Tests**: **103**
- **Passed Tests**: **103 passed in 20.45s**
- **Failed Tests**: **0**
- **Skipped Tests**: **0**

---

## 11. Known Limitations & Disclaimers

> [!WARNING]
> **Synthetic Simulation Notice**: All payment retry events, bank recovery probabilities, and evaluation streams in RecoverFlow are generated within a synthetic simulation environment (`simulator/ground_truth.py`). Performance on live merchant transaction data requires empirical validation on production payment gateway logs.
