# ⚡ RecoverFlow: Bandit-Optimized Payment Retry Scheduler

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Build Status](https://img.shields.io/badge/tests-63%20passed-brightgreen.svg)](tests/)

> An intelligent, context-aware payment retry scheduling engine powered by **Disjoint Contextual LinUCB** bandit algorithms and bounded safety rules. Replaces fixed retry schedules with contextual decision-making to optimize net revenue recovery while minimizing retry overhead.

---

## 📌 Executive Summary

When online payment transactions fail due to transient bank timeouts, insufficient funds, or gateway congestion, naive retry schedules (e.g. retrying fixed at 1 day, 3 days, 7 days) lead to high failure rates and unnecessary transaction fees. 

**RecoverFlow** dynamically selects the optimal retry delay (`1hr`, `6hr`, `1d`, `3d`, `7d`) based on structured transaction context (failure code, issuing bank, card network, day-of-month salary cycle, and attempt history).

### 🎯 Key Performance Highlights (Phase 1 Rigorous 10-Seed Benchmark)
All benchmark comparisons are evaluated under **Common Random Numbers (CRN)** and identical transaction streams across 10 random seeds (`[42, 101, 2026, 301, 402, 503, 604, 705, 806, 907]`):
- **vs. Fixed Schedule Baseline (`1d -> 3d -> 7d`)**: Mean Net Lift = **+INR 720,276.16** (**100% win rate 10/10 seeds**, 95% Bootstrap CI: `[+INR 594,362, +INR 854,925]`).
- **vs. Best Static Arm Baseline (`Always 3d`)**: Mean Net Lift = **+INR 212,413.07** (**90% win rate 9/10 seeds**, 95% Bootstrap CI: `[+INR 99,263, +INR 327,649]`). *Static arm was selected on 5 held-out validation seeds with ZERO test data leakage.*
- **vs. Contextual Heuristic Baseline**: Mean Net Lift = **+INR 183,394.80** (**90% win rate 9/10 seeds**, 95% Bootstrap CI: `[+INR 96,305, +INR 282,621]`).
- **vs. Oracle Upper Bound**: Oracle headroom gap = **+INR 367,743.11** (Oracle is evaluation-only).

---

## 🛡️ Phase 1 Evaluation Hardening Policies

The Phase 1 evaluation framework benchmark compares 5 distinct policies under strictly matched conditions:

1. **Fixed Schedule Baseline (`FixedSchedulePolicy`)**: Industry-standard naive sequence (Attempt 1 $\to$ `1d`, Attempt 2 $\to$ `3d`, Attempt 3 $\to$ `7d`).
2. **Best Static Arm Baseline (`BestStaticArmPolicy`)**: Frozen `Always 3d` arm selected via 5 held-out validation seeds (`[1001, 1002, 1003, 1004, 1005]`).
3. **Contextual Heuristic Baseline (`ContextualHeuristicPolicy`)**: Expert rule-based domain policy using observable context (failure code, salary cycle bucket, attempt number) with zero ground-truth access.
4. **RecoverFlow LinUCB (`LinUCBPolicy`)**: Reference disjoint LinUCB contextual bandit model ($\alpha=1.0, \text{min\_samples}=15$).
5. **Oracle Upper Bound (`OraclePolicy`)**: **Evaluation-Only Theoretical Upper Bound**. Evaluates ground-truth expected value $\mathbb{E}[R] = P_{\text{true}} \cdot \text{amount} - \text{cost}$, selecting optimal arm or stopping if $\max \mathbb{E}[R] \le 0$. Strictly isolated from production modules (`api/`, `policies/`).

---

## 🏗️ System Architecture & Workflow

```text
               Payment Failure Event
                         │
                         ▼
        ┌──────────────────────────────────┐
        │  19D Context Vector Encoder     │
        │  (Failure, Bank, Network, etc.)  │
        └────────────────┬─────────────────┘
                         │
                         ▼
        ┌──────────────────────────────────┐
        │   Eligibility & Hard-Stop Gate   │
        │   (Card Expired, Max Attempts)   │
        └────────────────┬─────────────────┘
                         │ Eligible
                         ▼
        ┌──────────────────────────────────┐
        │    Disjoint LinUCB Policy Engine │
        │    Score Arms: θ^T x + α √(x^T A⁻¹ x)
        └────────────────┬─────────────────┘
                         │ Best Delay Selected
                         ▼
        ┌──────────────────────────────────┐
        │    Expected-Value Stopping Rule  │
        │    (Halt if max θ^T x <= 0)      │
        └────────────────┬─────────────────┘
                         │ Execute Action
                         ▼
        ┌──────────────────────────────────┐
        │    Action Executor & Outcome     │
        │    (Reward = Recovered - Cost)   │
        └────────────────┬─────────────────┘
                         │ Feedback
                         ▼
        ┌──────────────────────────────────┐
        │    Online Learning Update        │
        │    A_a += x x^T,  b_a += r x     │
        └──────────────────────────────────┘
```

---

## 📂 Project Structure

```text
bandit_retry_scheduler/
├── api/                        # Production API Layer (Zero Ground-Truth Leakage)
│   ├── eligibility.py          # Eligibility Gate & Safety Rule Check
│   ├── decision_service.py     # Bandit Decision & Scoring Pipeline
│   ├── explainability.py       # Business Explanation Generator
│   ├── action_executor.py      # Bounded Execution & Safety Gate
│   ├── feedback_loop.py        # Online Policy Parameter Updater
│   └── audit_service.py        # Audit Trail & Logging Service
├── audit/                      # Evaluation Reports & Plot Artifacts
│   ├── evaluation_report.md    # Canonical Markdown Report
│   └── evaluation_results/phase1/
│       ├── phase1_static_arm_validation.json
│       ├── phase1_per_seed_results.json
│       ├── phase1_per_seed_results.csv
│       ├── phase1_summary.json
│       ├── phase1_paired_comparisons.json
│       └── PHASE1_EVALUATION_REPORT.md
├── evaluation/                 # Formal Evaluation Suite & Oracle
│   ├── harness.py              # Base Evaluation Harness
│   ├── metrics.py              # Performance & Regret Metrics
│   ├── plotting.py             # Plot Rendering Module
│   └── oracle.py               # Isolated Evaluation Oracle Policy
├── policies/                   # Policy Implementations
│   ├── base.py                 # Abstract Base Policy Interface
│   ├── fixed_schedule.py       # Canonical Baseline (1d -> 3d -> 7d)
│   ├── linucb.py               # Disjoint LinUCB Policy Implementation
│   ├── static_arm.py           # Static Arm & Best Static Arm Policies
│   └── heuristic.py            # Contextual Heuristic Policy
├── runner/                     # Simulation Engine
│   └── engine.py               # Policy Execution Engine with CRN Support
├── simulator/                  # Synthetic Environment Engine
│   ├── config.py               # Domain Enums & Constants
│   ├── environment.py          # Retry Simulator with CRN Support
│   ├── ground_truth.py         # Ground-Truth Recovery Probabilities (Isolated)
│   └── stream_generator.py     # Synthetic Transaction Generator
├── tests/                      # Pytest Unit Test Suite (63 Tests)
│   └── test_phase1_evaluation.py
├── run_phase1_evaluation.py    # Phase 1 Evaluation Hardening CLI Runner
├── dashboard.py                # Streamlit Merchant Interactive Dashboard
├── requirements.txt            # Runtime Dependencies
└── README.md                   # Submission Documentation
```

---

## ⚡ Quick Start & Installation

### 1. Clone & Setup Environment
```bash
git clone https://github.com/Seagull28/razorpay-revenue-recovery-bandit.git
cd bandit_retry_scheduler

# Create virtual environment
python -m venv .venv

# Activate environment (Windows PowerShell)
.venv\Scripts\Activate.ps1
# Activate environment (Linux/macOS)
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 🧪 Running Tests & Phase 1 Evaluation

### Execute Pytest Suite (63 Tests)
```bash
python -m pytest -q
```
*Target Result: All 63 tests pass with 0 failures and 0 collection errors.*

### Run Phase 1 Evaluation Benchmark Pipeline
```bash
python run_phase1_evaluation.py
```
*Generates raw artifacts and `PHASE1_EVALUATION_REPORT.md` in `audit/evaluation_results/phase1/`.*

---

## 🖥️ Launching the Merchant Dashboard

Launch the interactive single-page Streamlit dashboard:
```bash
streamlit run dashboard.py
```

The dashboard renders three stacked sections:
1. **Section 1: Executive Overview**: 5-policy benchmark summary table, 10-seed bootstrap CIs, and metrics cards.
2. **Section A: Interactive Simulation Mode**: Walkthrough of sample transactions, eligibility check, 5-arm score table, plain-language explanation, and live action execution with online parameter updates.
3. **Section C: Algorithmic Learning Insights**: Empirical evidence cards pairing quantitative findings with pre-rendered plots (`convergence_plots.png`, `drift_adaptation.png`).

---

## 🔌 Sim-to-Real Deployment Boundary

### Synthetic vs. Data-Agnostic Core
- **Synthetic Components**: `simulator/ground_truth.py` and `simulator/stream_generator.py` are strictly for evaluation.
- **Data-Agnostic Production Core**: `policies/linucb.py`, `api/eligibility.py`, `api/decision_service.py`, and `api/feedback_loop.py` operate purely on context vectors and realized rewards without referencing simulator logic.

### Production Gateway Integration Steps
1. Replace `simulator/` calls with real payment gateway event webhooks (e.g. Razorpay payment retry webhooks).
2. Feed real failure outcomes and transaction amounts into `process_outcome_and_update()`.
3. Persist model parameter matrices $\mathbf{A}_a$ and $\mathbf{b}_a$ to a reliable key-value store (e.g. Redis/PostgreSQL).

---

## ⚠️ Known Limitations & Disclaimers
1. **Synthetic Ground-Truth**: Benchmarks are evaluated within the synthetic simulation environment; production performance depends on real merchant transaction patterns.
2. **Oracle Theoretical Upper Bound**: The Oracle policy accesses ground-truth probabilities and is strictly an evaluation upper bound. It is **not deployable** and **not part of production code**.
3. **Model-Derived Probability Estimates**: Expected recovery probabilities in explainability strings are derived from learned linear reward estimates ($\hat{\theta}^T \mathbf{x}$), not direct calibrated probability classifiers.
4. **Interactive Dashboard Mode**: Re-running sample transactions in the dashboard updates an in-memory demonstration policy for educational purposes.

---

## 📜 License
Licensed under the [MIT License](LICENSE).
