# 🔬 Phase 3 Remaining Issues Analysis & Deep Correction Audit

## Executive Baseline Snapshot

- **Pytest Baseline**: 90 passed in 26.54s
- **Submission Verifier**: All 9 Stages Verified (Pass)
- **Phase 1 Fingerprint Hash**: `0580358a30ba`
- **RecoverFlow LinUCB Mean Net Revenue**: `INR 9,486,147.13`
- **Locked Core Files**: `policies/linucb.py`, `policies/encoder.py`, `simulator/ground_truth.py`

---

## 📌 Detailed Analysis of the 10 Audit Issues

### 1. Issue 1: Warm-Up / Training Semantics Audit
- **Current State**: Phase 3 evaluation pre-trains a `LinUCBPolicy` on 1,000 synthetic transactions from seed 42.
- **Audit Findings**:
  - Warm-up reward calculation: `reward = (amount_recovered if success else 0.0) - 10.0`, matching production reward semantics in `runner/engine.py` (`reward = (amount_recovered if success else 0.0) - self.retry_cost`).
  - Information leakage check: Warm-up uses `simulator.simulate_retry()` only for outcome feedback. `select_arm()` receives purely observable context. Zero oracle leakage.
  - Evaluation isolation: Warm-up seed (42) and evaluation stream seed (101) are independent.
  - Warm-up sensitivity: Warm-up sizes (0, 100, 500, 1000, 2000) show that score gaps mature after ~200 transactions and remain stable.

### 2. Issue 2 & 3: Magic Number Risk Penalties & Confidence Scale Calibration
- **Current State**:
  - Risk penalties currently use hardcoded INR constants: `ARM_RISK_PENALTY = {"3d": 0, "1d": 25, "6hr": 50, "1hr": 80, "7d": 120}`.
  - Confidence uses fixed absolute gap scaling: `confidence = min(1.0, max(0.0, raw_gap / 150.0))`.
- **Root Cause & Flaw**:
  - For a ₹500 transaction, a ₹150 gap is huge (30% of transaction amount). For a ₹50,000 transaction, a ₹150 gap is tiny (0.3%). Absolute gap scaling creates transaction amount scale bias!
- **Principled Fix**:
  1. Define a **normalized, dimensionless arm timing friction profile** $R_a \in [0.0, 1.0]$ based on retry delay properties:
     - `3d`: $0.10$ (Patient salary-cycle replenishment window — lowest operational friction)
     - `1d`: $0.25$ (Balanced daily processing window)
     - `6hr`: $0.45$ (Intraday retry — moderate congestion/timing friction)
     - `1hr`: $0.70$ (Immediate retry — high risk of retrying before customer/bank state changes)
     - `7d`: $0.85$ (Extended 7-day window — high opportunity-cost & churn risk)
  2. Implement **scale-aware relative score gap confidence**:
     $$\text{relative\_gap} = \frac{s_1 - s_2}{\max(|s_1|, 50.0)}$$
     $$\text{confidence} = \text{clip}\left(\frac{\text{relative\_gap}}{0.25}, 0.0, 1.0\right)$$
     This guarantees:
     - $0.0 \le \text{confidence} \le 1.0$
     - Scale-free & non-biased across low (₹500) and high (₹50,000) amounts!
     - Responds monotonically to decision margin.

### 3. Issue 4: Formal Objective Functions for Strategy Modes
- **Utility Optimization Definitions**:
  - **`MAXIMIZE_RECOVERY`**: Maximize raw policy utility $U_a = \text{UCB}_a$.
  - **`BALANCED`**: Maximize expected net revenue while penalizing uncertainty-weighted timing risk:
    $$U_a^{\text{balanced}} = \text{UCB}_a - \lambda_{\text{bal}} \cdot (1 - C) \cdot R_a \cdot \max(|\text{UCB}_a|, 50.0)$$
    where $\lambda_{\text{bal}} = 0.30$.
  - **`CONSERVATIVE`**: Maximize robust net revenue under high uncertainty and avoid extreme timing friction:
    $$U_a^{\text{conservative}} = \text{UCB}_a - \lambda_{\text{cons}} \cdot (1 - C) \cdot R_a \cdot \max(|\text{UCB}_a|, 50.0) - (25.0 \text{ if } a \in \{\text{1hr}, \text{7d}\} \text{ else } 0.0)$$
    where $\lambda_{\text{cons}} = 0.70$.

### 4. Issue 5 & 6: Arm Behavior Analysis & Actual Strategy Mode Simulation
- **Artifact 1**: `phase3_arm_behavior_analysis.json` — Per-arm success rate, average recovered value, retry cost, and net reward measured empirically from synthetic simulation streams.
- **Artifact 2**: `phase3_strategy_performance.json` — Evaluation of `MAXIMIZE_RECOVERY`, `BALANCED`, and `CONSERVATIVE` modes executed on the SAME 500-transaction simulation stream using Common Random Numbers (CRN), recording actual Net Revenue, Recovery Rate, Average Attempts, and Average Retry Cost.

### 5. Issue 7: Policy Update Executed Arm Verification
- **Audit Target**: `feedback_loop.py` / `action_executor.py` / `runner/engine.py`.
- **Finding**: When a strategy mode overrides raw recommendation $a_{\text{raw}}$ to $a_{\text{final}}$, `execute_retry_action()` executes $a_{\text{final}}$, and `process_outcome_and_update()` updates `policy.update(tx, a_{\text{final}}, reward)`.
- **Action**: Add explicit test `test_strategy_selected_arm_updates_correct_policy_arm()`.

### 6. Issue 8 & 9: API Contract & Audit Trail Verification
- Ensure public payloads explicitly expose:
  - `raw_policy_arm`: Raw LinUCB recommendation.
  - `recommended_delay`: Final strategy recommendation.
- Audit trail logs both `raw_policy_arm` and `final_recommended_arm` without overwriting keys.

---
