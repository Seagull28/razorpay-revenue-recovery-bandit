# ⚡ RecoverFlow: Bandit-Optimized Payment Retry Scheduler

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Build Status](https://img.shields.io/badge/tests-50%20passed-brightgreen.svg)](tests/)

> An intelligent, context-aware payment retry scheduling engine powered by **Disjoint Contextual LinUCB** bandit algorithms and bounded safety rules. Replaces fixed retry schedules with contextual decision-making to optimize net revenue recovery while minimizing retry overhead.

---

## 📌 Executive Summary

When online payment transactions fail due to transient bank timeouts, insufficient funds, or gateway congestion, naive retry schedules (e.g. retrying fixed at 1 day, 3 days, 7 days) lead to high failure rates and unnecessary transaction fees. 

**RecoverFlow** dynamically selects the optimal retry delay (`1hr`, `6hr`, `1d`, `3d`, `7d`) based on structured transaction context (failure code, issuing bank, card network, day-of-month salary cycle, and attempt history).

### 🎯 Key Performance Highlights (Synthetic Benchmark)
- **Mean Net Revenue Lift**: **+15.34%** across 10 random seeds (**95% Bootstrap CI: [+11.50%, +18.86%]**).
- **Seed 42 Recovery Rate**: **66.20%** (+14.03% over fixed-schedule baseline).
- **Segment Convergence**: Reaches **93.15%** recovery rate on `issuer_timeout` (+79.74% revenue lift) and automatically adapts to non-stationary bank policy drift.

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

## 🧮 Mathematical Model: Disjoint LinUCB

For each candidate retry delay arm $a \in \{\text{1hr}, \text{6hr}, \text{1d}, \text{3d}, \text{7d}\}$, the policy maintains ridge regression parameters $\mathbf{A}_a \in \mathbb{R}^{19 \times 19}$ and $\mathbf{b}_a \in \mathbb{R}^{19}$.

### 1. Point Estimate & Exploration Bonus
Given a 19-dimensional context vector $\mathbf{x}$, the point estimate of expected net revenue is:
$$\hat{\theta}_a = \mathbf{A}_a^{-1} \mathbf{b}_a, \quad \text{Point Estimate} = \hat{\theta}_a^T \mathbf{x}$$

The Upper Confidence Bound (UCB) selection score is:
$$\text{UCB}_a = \hat{\theta}_a^T \mathbf{x} + \alpha \sqrt{\mathbf{x}^T \mathbf{A}_a^{-1} \mathbf{x}}$$

### 2. Learned Stopping Rule vs. Safety Safeguards
- **Learned Stopping**: Retry is halted if $\max_{a} (\hat{\theta}_a^T \mathbf{x}) \le 0$ after accumulating sufficient experience.
- **Cold-Start Protection**: Stopping rule evaluation is deferred until an arm collects $\ge 15$ samples (`min_samples_for_stopping = 15`) to prevent premature stopping.
- **Hard Safety Rules**: Transactions with expired cards (on attempt $>1$), previous payment recoveries, or attempt count $>4$ are halted immediately by `EligibilityGate`.

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
│   ├── evaluation_report.md    # 11-Section Comprehensive Report
│   ├── item2_multiseed_results.json
│   ├── item3_adaptive_results.json
│   ├── item4_alpha_results.json
│   └── plots/                  # Generated Empirical PNG Plots
├── policies/                   # Policy Implementations
│   ├── base.py                 # Abstract Base Policy Interface
│   ├── fixed_schedule.py       # Canonical Baseline (1d -> 3d -> 7d)
│   └── linucb.py               # Disjoint LinUCB Policy Implementation
├── runner/                     # Simulation Engine
│   └── engine.py               # Policy Execution Engine & Metrics Collector
├── simulator/                  # Synthetic Environment Engine
│   ├── config.py               # Domain Enums & Constants
│   ├── environment.py          # Retry Simulator & Cost Calculator
│   ├── ground_truth.py         # Ground-Truth Recovery Probabilities (Isolated)
│   └── stream_generator.py     # Synthetic Transaction Generator
├── tests/                      # Pytest Unit Test Suite (50 Tests)
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

## 🧪 Running Tests

Execute the complete, portable test suite:
```bash
pytest -q
```
*Target Result: All tests pass with 0 failures and 0 collection errors.*

---

## 🖥️ Launching the Merchant Dashboard

Launch the interactive single-page Streamlit dashboard:
```bash
streamlit run dashboard.py
```

The dashboard renders three stacked sections:
1. **Section 1: Executive Overview**: High-level net revenue metrics, 10-seed bootstrap CIs, and per-segment breakdowns.
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

## ⚠️ Known Limitations
1. **Synthetic Ground-Truth**: Benchmarks are evaluated within the synthetic simulation environment; production performance depends on real merchant transaction patterns.
2. **Model-Derived Probability Estimates**: Expected recovery probabilities are derived from learned linear reward estimates ($\hat{\theta}^T \mathbf{x}$), not direct calibrated probability classifiers.
3. **Interactive Dashboard Mode**: Re-running sample transactions in the dashboard updates an in-memory demonstration policy for educational purposes.

---

## 📜 License
Licensed under the [MIT License](LICENSE).
