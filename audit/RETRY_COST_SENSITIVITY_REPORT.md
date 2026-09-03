# 📊 RECOVERFLOW RETRY COST REALISM SENSITIVITY REPORT

> **Post-Hoc Sensitivity Analysis of Payment Retry Costs across Delay Arms**

---

## 1. Executive Summary & Context

In the canonical Phase 1 benchmark evaluation, retry costs were modeled using a flat simplification (`DEFAULT_RETRY_COST = 10.0 INR` per retry attempt across all delay arms). In real-world payment gateway environments:
- **Faster retries (`1hr`, `6hr`)** carry higher gateway/network processing and rate-limiting fees.
- **Baseline retries (`1d`)** reflect standard processing costs (~10.0 INR).
- **Longer delays (`3d`, `7d`)** carry customer friction, opportunity cost of delayed settlement, and higher dispute/drop-off risk.

To evaluate whether RecoverFlow's performance superiority holds up under non-flat, realistic retry cost structures without modifying the locked canonical Phase 1 benchmark pipeline (`configuration_fingerprint: 0580358a30ba`), a post-hoc sensitivity analysis was conducted.

---

## 2. Alternative Cost Table & Sensitivity Setup

The post-hoc sensitivity script (`audit/retry_cost_sensitivity_analysis.py`) recomputed total retry costs and net revenues from the checked-in 10-seed Phase 1 audit log (`audit/evaluation_results/phase1/phase1_per_seed_results.json`) using the following illustrative per-arm cost table:

| Delay Arm | Canonical Flat Cost | Alternative Realistic Cost | Cost Rationale |
| :---: | :---: | :---: | :--- |
| **`1hr`** | 10.0 INR | **18.0 INR** | High gateway rate-limiting fees & network congestion surcharges |
| **`6hr`** | 10.0 INR | **14.0 INR** | Moderate gateway processing surcharge |
| **`1d`** | 10.0 INR | **10.0 INR** | Standard baseline retry processing cost |
| **`3d`** | 10.0 INR | **12.0 INR** | Moderate customer fatigue & settlement delay cost |
| **`7d`** | 10.0 INR | **15.0 INR** | High customer drop-off risk & capital lockup cost |

---

## 3. Empirical Sensitivity Results (10 Random Seeds)

### A. Mean Net Revenue Comparison

| Policy Name | Canonical Flat Cost Net Rev | Alt Realistic Cost Net Rev | Net Revenue Change | Net Change (%) |
| :--- | :---: | :---: | :---: | :---: |
| **RecoverFlow LinUCB** | **INR 9,486,147.13** | **INR 9,463,394.73** | **-INR 22,752.40** | **-0.24%** |
| **Best Static Arm (`3d`)** | INR 9,273,734.06 | INR 9,259,328.66 | -INR 14,405.40 | -0.16% |
| **Contextual Heuristic** | INR 9,302,752.33 | INR 9,285,853.73 | -INR 16,898.60 | -0.18% |
| **Fixed Schedule (`1d->3d->7d`)** | INR 8,765,870.96 | INR 8,748,930.77 | -INR 16,940.20 | -0.19% |

### B. Net Revenue Lift & Win-Rate Stability

| Baseline Policy | Canonical Flat-Cost Net Lift | Alt Realistic-Cost Net Lift | Alt Win Rate (10 Seeds) | Alt Paired 95% Bootstrap CI |
| :--- | :---: | :---: | :---: | :---: |
| **vs. Fixed Schedule** | **+INR 720,276.16** | **+INR 714,463.96** | **10 / 10 (100%)** | `[+INR 591,045.59, +INR 850,546.39]` |
| **vs. Best Static Arm** | **+INR 212,413.07** | **+INR 204,066.07** | **9 / 10 (90%)** | `[+INR 91,246.71, +INR 318,245.38]` |
| **vs. Contextual Heuristic** | **+INR 183,394.80** | **+INR 177,541.00** | **9 / 10 (90%)** | `[+INR 89,570.48, +INR 276,631.00]` |

---

## 4. Key Findings & Conclusion

1. **Robust Performance Advantage**: Under the alternative per-arm cost structure, RecoverFlow LinUCB maintains a **+INR 714,463.96** net revenue lift over the Fixed Schedule baseline (**100% win rate across 10/10 seeds**) and a **+INR 204,066.07** net lift over the Best Static Arm (**90% win rate across 9/10 seeds**).
2. **Lift Stability**: Net revenue lift vs Fixed Schedule shrinks by less than **0.81%** (-INR 5,812.20), and lift vs Best Static Arm shrinks by only **3.93%** (-INR 8,347.00).
3. **Conclusion**: RecoverFlow's contextual bandit optimization superiority is highly robust to non-flat retry cost structures.

> [!NOTE]
> **Sensitivity Scope Notice**: This post-hoc sensitivity study uses illustrative cost assumptions (`18.0/14.0/10.0/12.0/15.0 INR`) to test model robustness. It does not represent measured Razorpay production gateway fee structures.
