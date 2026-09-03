# ⚡ RecoverFlow: Bandit-Optimized Payment Retry Scheduler

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Build Status](https://img.shields.io/badge/tests-70%20passed-brightgreen.svg)](tests/)

> An intelligent, context-aware payment retry scheduling engine powered by **Disjoint Contextual LinUCB** bandit algorithms and bounded safety rules. Replaces fixed retry schedules with contextual decision-making to optimize net revenue recovery while minimizing retry overhead.

---

> [!WARNING]
> **Simulation Notice:** All payment events, recovery probabilities, revenue figures, and benchmark results in RecoverFlow are generated using a synthetic simulation environment. No Razorpay production data, merchant data, or real customer payment data is used.

---

## 📌 Executive Summary

When online payment transactions fail due to transient bank timeouts, insufficient funds, or gateway congestion, naive retry schedules (e.g. retrying fixed at 1 day, 3 days, 7 days) lead to high failure rates and unnecessary transaction fees. 

**RecoverFlow** dynamically selects the optimal retry delay (`1hr`, `6hr`, `1d`, `3d`, `7d`) based on structured transaction context (failure code, issuing bank, card network, day-of-month salary cycle, and attempt history).

### 🎯 Key Performance Highlights (Phase 1 Rigorous 10-Seed Benchmark)
All benchmark comparisons are evaluated under **Common Random Numbers (CRN)** and identical transaction streams across 10 random seeds (`[42, 101, 2026, 301, 402, 503, 604, 705, 806, 907]`):
- **vs. Fixed Schedule Baseline (`1d -> 3d -> 7d`)**: Mean Net Lift = **+INR 720,276.16** (**100% win rate 10/10 seeds**, 95% Bootstrap CI: `[+INR 594,362, +INR 854,925]`).
- **vs. Best Static Arm Baseline (`Always 3d`)**: Mean Net Lift = **+INR 212,413.07** (**90% win rate 9/10 seeds**, 95% Bootstrap CI: `[+INR 99,263, +INR 327,649]`). *Static arm was selected on 5 held-out validation seeds with ZERO test data leakage.*
- **vs. Contextual Heuristic Baseline**: Mean Net Lift = **+INR 183,394.80** (**90% win rate 9/10 seeds**, 95% Bootstrap CI: `[+INR 96,305, +INR 282,621]`).
- **vs. Ground-Truth Greedy Oracle**: Oracle headroom gap = **+INR 367,743.11** (Oracle is evaluation-only).

---

## 🛡️ Benchmark Evaluation Policies

The evaluation framework benchmark compares 5 distinct policies under strictly matched conditions:

1. **Fixed Schedule Baseline (`FixedSchedulePolicy`)**: Naive sequence (Attempt 1 $\to$ `1d`, Attempt 2 $\to$ `3d`, Attempt 3 $\to$ `7d`).
2. **Best Static Arm Baseline (`BestStaticArmPolicy`)**: Frozen `Always 3d` arm selected via 5 held-out validation seeds (`[1001, 1002, 1003, 1004, 1005]`).
3. **Contextual Heuristic Baseline (`ContextualHeuristicPolicy`)**: Expert rule-based domain policy using observable context (failure code, salary cycle bucket, attempt number) with zero ground-truth access.
4. **RecoverFlow LinUCB (`LinUCBPolicy`)**: Reference disjoint LinUCB contextual bandit model ($\alpha=1.0, \text{min\_samples}=15$).
5. **Ground-Truth Greedy Oracle (`OraclePolicy`)**: **Evaluation-Only Theoretical Reference Benchmark**. Evaluates ground-truth expected value $\mathbb{E}[R] = P_{\text{true}} \cdot \text{amount} - \text{cost}$, selecting optimal arm or stopping if $\max \mathbb{E}[R] \le 0$. Strictly isolated from production modules (`api/`, `policies/`, `runner/`).

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
├── LICENSE                     # MIT License File
├── pyproject.toml              # Python Package Configuration
├── requirements.txt            # Runtime Dependencies
├── README.md                   # Submission Documentation
├── verify_submission.py        # Single-Command Submission Verification Runner
├── run_phase1_evaluation.py    # Phase 1 Evaluation CLI Harness
├── dashboard.py                # Streamlit Merchant Interactive Dashboard
├── create_project_zip.py       # Submission Packaging Utility
├── conftest.py                 # Pytest Root Package Resolver
├── api/                        # Production API Layer (Zero Ground-Truth Leakage)
├── audit/                      # Evaluation Reports & Plot Artifacts
├── core/                       # Neutral Context Utilities
├── evaluation/                 # Formal Evaluation Suite & Oracle
├── policies/                   # Policy Implementations
├── runner/                     # Simulation Engine
├── simulator/                  # Synthetic Environment Engine
└── tests/                      # Pytest Unit Test Suite (70 Tests)
```

---

## ⚡ Quick Start & Evaluator Workflow

### Environment Compatibility
- **Tested Python Version**: **Python 3.11.9** (Intended compatibility: Python 3.9+)
- **Operating Systems**: Windows, macOS, Linux

### 1. Clone & Enter Directory
```bash
git clone https://github.com/Seagull28/razorpay-revenue-recovery-bandit.git
cd bandit_retry_scheduler
```

### 2. Create & Activate Virtual Environment
```bash
# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1

# Linux / macOS
python -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run Single-Command Submission Verification
```bash
python verify_submission.py
```
*Executes all 9 verification stages (Environment, Structure, Imports, AST Ground-Truth Isolation, Pytest Suite, Phase 1 Benchmark, Artifact Schema Validation, Deterministic Reproducibility, Synthetic Disclosures).*

### 5. Run Phase 1 Benchmark Evaluation Harness
```bash
python run_phase1_evaluation.py
```
*Generates canonical artifacts in `audit/evaluation_results/phase1/`.*

### 6. Launch Interactive Merchant Dashboard
```bash
streamlit run dashboard.py
```

---

## 🔌 Sim-to-Real Deployment Boundary

### Synthetic vs. Data-Agnostic Core
- **Synthetic Components**: `simulator/ground_truth.py` and `simulator/stream_generator.py` are strictly for evaluation.
- **Data-Agnostic Production Core**: `policies/linucb.py`, `api/eligibility.py`, `api/decision_service.py`, and `api/feedback_loop.py` operate purely on context vectors and realized rewards without referencing simulator logic.

---

## ⚠️ Known Limitations & Disclaimers
1. **Synthetic Simulation**: Benchmarks are evaluated within the synthetic simulation environment; production performance depends on real merchant transaction patterns.
2. **Ground-Truth Greedy Oracle**: The Oracle policy accesses ground-truth probabilities and is strictly an evaluation benchmark. It is **not deployable** and **not part of production code**.
3. **Model-Derived Probability Estimates**: Expected recovery probabilities in explainability strings are derived from learned linear reward estimates ($\hat{\theta}^T \mathbf{x}$), not direct calibrated probability classifiers.

---

## 📜 License
Licensed under the [MIT License](LICENSE).
