# ⚡ RecoverFlow: Bandit-Optimized Payment Retry Scheduler

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Build Status](https://img.shields.io/badge/tests-222%20passed-brightgreen.svg)](tests/)
[![Verification](https://img.shields.io/badge/verify__submission.py-16%2F16%20stages-brightgreen.svg)](verify_submission.py)

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
- **Contextual Adaptation**: Outperforms heuristic rules and static schedules while approaching theoretical Ground-Truth Oracle performance (recovering **71.42%** of maximum possible net revenue vs **58.20%** for fixed schedule).

---

## 🛡️ Benchmark Evaluation Policies

The evaluation framework benchmark compares 5 distinct policies under strictly matched conditions:

1. **Fixed Schedule Baseline (`FixedSchedulePolicy`)**: Naive sequence (Attempt 1 $\to$ `1d`, Attempt 2 $\to$ `3d`, Attempt 3 $\to$ `7d`).
2. **Best Static Arm Baseline (`BestStaticArmPolicy`)**: Frozen `Always 3d` arm selected via 5 held-out validation seeds (`[1001, 1002, 1003, 1004, 1005]`).
3. **Contextual Heuristic Baseline (`ContextualHeuristicPolicy`)**: Expert rule-based domain policy using observable context (failure code, salary cycle bucket, attempt number) with zero ground-truth access.
4. **RecoverFlow LinUCB (`LinUCBPolicy`)**: Reference disjoint LinUCB contextual bandit model ($\alpha=1.0, \text{min\_samples}=15$).
5. **Ground-Truth Greedy Oracle (`OraclePolicy`)**: **Evaluation-Only Theoretical Reference Benchmark**. Evaluates ground-truth expected value $\mathbb{E}[R] = P_{\text{true}} \cdot \text{amount} - \text{cost}$, selecting optimal arm or stopping if $\max \mathbb{E}[R] \le 0$. Strictly isolated from production modules (`api/`, `policies/`, `runner/`).

---

## 🔄 RecoverFlow V1 vs. RecoverFlow V2

RecoverFlow includes two verified engine architectures:

| Feature / Dimension | RecoverFlow V1 (Canonical Baseline) | RecoverFlow V2 (Primary Recovery Engine) |
| :--- | :--- | :--- |
| **Action Space** | Delay-Only (`1hr`, `6hr`, `1d`, `3d`, `7d`) | **Action-Aware (16 Actions)** across CARD, UPI, NETBANKING channels (Delays + Payment-Method Switching) |
| **Stopping Rule** | Post-hoc LinUCB $\max \hat{\theta}^T x \le 0$ | **Decision-Time Economic EV Feasibility Gate** ($\hat{P}(\text{success} \mid x, a) \cdot \text{Amount} - \text{Cost}(a) > 0$) |
| **Cold-Start Handling** | UCB Exploration Bonus | Decoupled Logistic Probability Estimator with Optimistic Prior ($p_{\text{prior}} = 0.35$) |
| **Benchmark Suite** | 10-Seed CRN Suite (10,000 transactions) | **5-Seed CRN Benchmark (15,000 transactions)** |
| **Benchmark Result** | +INR 720k Net Lift over Fixed Schedule | **92.24% Recovery Rate (+73.87% net value gain, INR 10.74M net reward)** |
| **Evaluation Primary Status** | Verified Foundation Baseline | **Primary Submission System** for multi-channel autonomous recovery |

> **Primary System Designation**: **RecoverFlow V2** is the primary recovery engine representing RecoverFlow's full autonomous multi-channel payment recovery capabilities. RecoverFlow V1 is preserved as the immutable, fully verified baseline foundation.

---

## 🏗️ System Architecture & Workflow

RecoverFlow is one layered system with two independent decision engines: a locked V1 baseline and V2, the primary action-aware engine. All live interfaces (the Razorpay webhook adapter, the Streamlit dashboard, and the thin HTTP API) call into V2 — V1 is exercised only by the Phase 1 canonical benchmark, never by live traffic.

![RecoverFlow system architecture](docs/diagrams/architecture_overview.png)

### How one V2 decision is actually made

The diagram below traces a single failed transaction end to end — the exact payload at each step, from the raw Razorpay webhook through eligibility checks, economic EV estimation, LinUCB scoring, the combined decision, and the online feedback update that follows execution.

![RecoverFlow V2 decision workflow](docs/diagrams/v2_decision_workflow.png)

### V1's decision loop, in detail

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

## 🧠 Phase 3: Product Differentiation & Intelligence Layer

RecoverFlow includes three major merchant-facing intelligence capabilities:

1. **Recovery Strategy Intelligence (`core/strategy.py`)**:
   - Maps raw retry arm choices (`1hr`, `6hr`, `1d`, `3d`, `7d`) into human-readable strategy categories (`IMMEDIATE_RECOVERY`, `FAST_RETRY`, `BALANCED_RETRY`, `PATIENT_RECOVERY`, `LAST_CHANCE_RECOVERY`).
   - Calculates **Decision Separation Confidence (0.0 to 1.0)** based on relative score gap between top candidate retry windows. Confidence is scale-aware for normal decision magnitudes and uses a stability floor (50.0 INR) near zero.
   - Classifies **Decision Stability** (`STABLE`, `MODERATELY_STABLE`, `UNSTABLE`) with deterministic thresholding.
   - Ranks alternative retry strategies with relative policy scores.

2. **Risk-Aware Recovery Intelligence (`core/risk.py`)**:
   - Implements merchant **Strategy Modes** (`MAXIMIZE_RECOVERY`, `BALANCED`, `CONSERVATIVE`) using dimensionless friction profiles ($R_a, E_a \in [0.0, 1.0]$) without fixed INR penalties.
   - Computes structured **Risk Profiles** (`risk_score`, `risk_level`, `risk_factors`) using strictly observable context.

3. **Merchant Recovery Insights & Opportunity Scoring (`analytics/recovery_insights.py`)**:
   - Aggregates transaction outcomes across observable context dimensions (`failure_code`, `amount_bucket`, `bank`, `day_of_month_bucket`).
   - Computes a normalized **Recovery Opportunity Score (0 to 100)** to identify high-value prioritization targets.

---

## 🌊 Phase 4B: Robustness Under Environment Shift

RecoverFlow's contextual bandit policy was evaluated across 3 environmental scenarios to test adaptability under non-stationary distributions (`simulator/scenario_environment.py`). When insufficient-funds failures rise from 38% to 60% of the transaction stream (`high_insufficient_funds`), LinUCB's net revenue advantage over Fixed Schedule **expands from +INR 672,174.83 to approximately +INR 844,656.03** (+9.10% recovery rate lift) by learning to defer NSF retries to optimal salary-cycle windows. Under an inverted failure distribution combined with a 30% reduction in overall recovery probability (`distribution_shift`), LinUCB's net revenue lift **expands to approximately +INR 1,377,950.09** (+23.49% recovery rate lift) while reducing retry attempt overhead by 22.9% (figures approximate; see [`audit/PHASE4B_ROBUSTNESS_REPORT.md`](audit/PHASE4B_ROBUSTNESS_REPORT.md) for the tolerance-based reproducibility methodology). For full methodology, configuration details, and 3-seed benchmark results, see [`audit/PHASE4B_ROBUSTNESS_REPORT.md`](audit/PHASE4B_ROBUSTNESS_REPORT.md).

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
├── run_phase3_evaluation.py    # Phase 3 Product Intelligence CLI Harness
├── run_phase4_strategy_diagnostics.py # Phase 4A Strategy Intelligence Diagnostics Harness
├── run_phase4b_robustness.py   # Phase 4B Robustness Evaluation CLI Harness
├── dashboard.py                # Streamlit Merchant Control Center Dashboard
├── create_project_zip.py       # Submission Packaging Utility
├── conftest.py                 # Pytest Root Package Resolver
├── analytics/                  # Merchant Recovery Insights & Opportunity Scoring Engine
├── api/                        # Production API Layer (Zero Ground-Truth Leakage)
│   └── intelligence_service.py # Phase 3 Recovery Intelligence API
├── audit/                      # Evaluation Reports & Plot Artifacts
│   ├── PARAMETER_REGISTRY.md   # Parameter Classification & Transparency Registry
│   ├── evaluation_results/phase1/  # Canonical Phase 1 Artifacts
│   ├── evaluation_results/phase3/  # Phase 3 Intelligence Evaluation Artifacts
│   ├── evaluation_results/phase4_strategy_diagnostics/ # Phase 4A Diagnostic Artifacts
│   └── evaluation_results/phase4b_robustness/ # Phase 4B Robustness Evaluation Artifacts
├── core/                       # Recovery Strategy & Risk Intelligence Engines
│   ├── config.py               # Centralized Strategy & Risk Constants
│   ├── strategy.py             # Strategy Classification & Confidence Engine
│   └── risk.py                 # Risk Profiling & Strategy Mode Engine
├── evaluation/                 # Formal Evaluation Suite & Oracle
├── policies/                   # Policy Implementations
├── runner/                     # Simulation Engine
├── simulator/                  # Synthetic Environment Engine
├── service/                    # Thin HTTP API + Razorpay Webhook Adapter (FastAPI)
│   ├── http_api.py             # /health, /v1/webhooks/razorpay, /v1/recovery/decide
│   └── razorpay_adapter.py     # Real Razorpay payload -> internal transaction context
├── docs/diagrams/               # Architecture & workflow diagrams
└── tests/                      # Pytest Unit Test Suite (222 Tests)
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
*Executes all 16 verification stages (Environment, Structure, Imports, AST Ground-Truth Isolation, V1 Locked-File Integrity, Pytest Suite, Dashboard Smoke Testing, Phase 1 Benchmark, Artifact Schema Validation, Phase 1 Deterministic Reproducibility, Phase 3/4A Strategy Diagnostics, Phase 4B Robustness, Offline V2 Artifact Validation, V2 Evaluation Reproducibility, Package Installation & External Import, Synthetic Disclosures).*

### 5. Run Phase 1 Benchmark Evaluation Harness
```bash
python run_phase1_evaluation.py
```
*Generates canonical artifacts in `audit/evaluation_results/phase1/`.*

### 6. Launch Interactive Merchant Dashboard
```bash
streamlit run dashboard.py
```

### 7. Run Phase 4A Strategy Intelligence Diagnostics
```bash
python run_phase4_strategy_diagnostics.py
```
*Evaluates 5,000 deterministic CRN transactions across `MAXIMIZE_RECOVERY`, `BALANCED`, and `CONSERVATIVE` strategy modes over a warmed LinUCB policy state.*

- **What it evaluates**: Policy confidence, score gaps, ambiguity tier distributions, transition matrices, failure code & transaction amount segmentations, low-confidence decision subsets, and counterfactual risk-weight sensitivity.
- **Key Empirical Finding**: Low global strategy divergence (2.32%) is **intended and healthy product behavior**. High policy confidence ($C \ge 0.50$, 94.16% of transactions) naturally decays risk adjustments to preserve optimal net revenue recovery. When decision confidence is low / score gap is narrow (the 10% ambiguous decision subset), strategy modes activate aggressively with a **22.97% disagreement rate** and a **35.84% CONSERVATIVE override rate**.
- **Reports & Audit Provenance**:
  - [`audit/COMPLIANCE_DISCLOSURE.md`](audit/COMPLIANCE_DISCLOSURE.md)
  - [`audit/RETRY_COST_SENSITIVITY_REPORT.md`](audit/RETRY_COST_SENSITIVITY_REPORT.md)
  - [`audit/PARAMETER_REGISTRY.md`](audit/PARAMETER_REGISTRY.md)
  - [`audit/PHASE4B_ROBUSTNESS_REPORT.md`](audit/PHASE4B_ROBUSTNESS_REPORT.md)
  - [`audit/PHASE4_STRATEGY_INTELLIGENCE_REPORT.md`](audit/PHASE4_STRATEGY_INTELLIGENCE_REPORT.md)
  - [`v2_evaluation_results.json`](v2_evaluation_results.json)

---

## 🔌 Sim-to-Real Deployment Boundary

### Synthetic vs. Data-Agnostic Core
- **Synthetic Components**: `simulator/ground_truth.py`, `simulator/v2_ground_truth.py`, and `simulator/stream_generator.py` are strictly for evaluation.
- **Data-Agnostic Production Core**: `policies/linucb.py`, `policies/v2_linucb.py`, `api/v2_decision_service.py`, `core/v2_ev_estimator.py`, and `api/v2_feedback_loop.py` operate purely on context vectors and realized rewards without referencing simulator logic.

---

## 🔌 HTTP API & Deployability

RecoverFlow ships a thin FastAPI service (`service/http_api.py`) and a Razorpay webhook adapter (`service/razorpay_adapter.py`) proving the V2 decision logic is cleanly callable over HTTP — not just from the dashboard or CLI scripts.

**Endpoints:**
- `GET /health` — liveness check
- `POST /v1/webhooks/razorpay` — accepts a real Razorpay `payment.failed` webhook payload (paise amounts, `error_reason` codes, card/UPI/netbanking method shapes), parses it via the adapter, and returns a V2 decision
- `POST /v1/recovery/decide` — accepts an already-normalized transaction context directly, for integration testing without a real webhook

**Run it:**
```bash
uvicorn service.http_api:app --port 8000
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/v1/webhooks/razorpay \
  -H "Content-Type: application/json" \
  -d '{"entity":"event","event":"payment.failed","payload":{"payment":{"entity":{"id":"pay_example","amount":250000,"method":"card","card":{"network":"Visa"},"error_reason":"insufficient_funds","created_at":1735689600}}}}'
```

**Honest scope:** this is a proof-of-concept, not a hardened production service — no database, no authentication, no persistence beyond a single in-process policy instance. It demonstrates that the decision logic is cleanly separable from the dashboard and safely callable over a real network boundary; wrapping it with persistence and auth is the deliberate next step, not an oversight.

Covered by `tests/test_http_api.py` (7 tests: health check, valid webhook parsing, card-expired eligibility handling, malformed-payload rejection, direct-decision endpoint, and confirmation that no internal stack trace ever leaks to an external caller on error).

---

## ⚠️ Known Limitations & Disclaimers
1. **Synthetic Simulation**: Benchmarks are evaluated within the synthetic simulation environment; production performance depends on real merchant transaction patterns.
2. **Ground-Truth Greedy Oracle**: The Oracle policy accesses ground-truth probabilities and is strictly an evaluation benchmark. It is **not deployable** and **not part of production code**.
3. **Model-Derived Probability Estimates**: Expected recovery probabilities in explainability strings are derived from learned linear reward estimates ($\hat{\theta}^T \mathbf{x}$), not direct calibrated probability classifiers.
4. **Regulatory Scope**: RecoverFlow does not model India-specific recurring-payment retry regulations (e.g. RBI/NPCI e-mandate retry attempt and window rules). See [`audit/COMPLIANCE_DISCLOSURE.md`](audit/COMPLIANCE_DISCLOSURE.md) for a full disclosure of this scope boundary.
5. **Flat Retry Cost Model**: `DEFAULT_RETRY_COST` is a single constant across all delay arms in the canonical Phase 1 evaluation. See [`audit/RETRY_COST_SENSITIVITY_REPORT.md`](audit/RETRY_COST_SENSITIVITY_REPORT.md) for a post-hoc sensitivity analysis under a more realistic per-arm cost assumption.
6. **V2 Synthetic Action Cost Model**: V2 models action costs as ₹10 for timed retries and ₹15 for payment-method switching. These values are illustrative benchmark parameters rather than measured production gateway fees.
7. **Decoupled EV Estimator Optimistic Prior**: V2's `V2EVEstimator` initializes with an optimistic success probability prior ($p_{\text{prior}} = 0.35$) to enable safe economic stopping without premature cold-start shutdown.

---

## 📜 License
Licensed under the [MIT License](LICENSE).
