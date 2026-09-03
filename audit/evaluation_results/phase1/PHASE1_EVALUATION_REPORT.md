# 🛡️ RecoverFlow Phase 1: Evaluation Hardening Report

## Executive Summary
This document presents the rigorous, fair, and reproducible Phase 1 evaluation benchmark for RecoverFlow. All policies were evaluated under **Common Random Numbers (CRN)** and identical transaction streams across 10 benchmark seeds.

### Policy Performance Summary (10 Benchmark Seeds)
| Policy Name | Mean Net Revenue (INR) | Mean Recovery Rate (%) | Mean Retry Cost (INR) | Mean Attempts |
| :--- | :---: | :---: | :---: | :---: |
| **Fixed Schedule** | ₹8,765,870.96 | 66.97% | ₹76,379.00 | 7637.9 |
| **Best Static Arm** | ₹9,273,734.06 | 70.06% | ₹72,027.00 | 7202.7 |
| **Contextual Heuristic** | ₹9,302,752.33 | 76.43% | ₹64,034.00 | 6403.4 |
| ⭐ **RecoverFlow LinUCB** | ₹9,486,147.13 | 77.16% | ₹62,504.00 | 6250.4 |
| 🔮 **Oracle Upper Bound** | ₹9,853,890.23 | 86.92% | ₹57,457.00 | 5745.7 |

## 1. Static Arm Validation (Held-Out Seeds)
To prevent evaluation data leakage, the **Best Static Arm** was selected by evaluating all 5 static arms across 5 held-out validation seeds `[1001, 1002, 1003, 1004, 1005]`. The benchmark seeds had ZERO influence on selection.

- **Frozen Selected Arm**: `Always 3d`
- **Validation Mean Net Revenue Breakdown**:
  - `Always 1hr`: ₹3,405,881.07
  - `Always 6hr`: ₹4,683,595.62
  - `Always 1d`: ₹7,500,060.10
  - `Always 3d`: ₹9,157,030.54 (Selected)
  - `Always 7d`: ₹8,314,715.30

## 2. Paired Seed-Level Delta Comparisons & Bootstrap CIs
All comparisons represent **paired seed-level deltas** ($\Delta_{\text{seed}} = \text{LinUCB} - \text{Baseline}$) with 10,000 bootstrap resamples.

| Comparison Pair | Mean Lift (INR) | Win Rate | 95% Bootstrap CI |
| :--- | :---: | :---: | :---: |
| RecoverFlow vs. Fixed Schedule | +₹720,276.16 | 100.0% (10/10) | [+594,361.86, +854,925.27] |
| RecoverFlow vs. Best Static Arm (`3d`) | +₹212,413.07 | 90.0% (9/10) | [+99,262.66, +327,648.66] |
| RecoverFlow vs. Contextual Heuristic | +₹183,394.80 | 90.0% (9/10) | [+96,304.80, +282,620.55] |
| Oracle Upper Bound vs. RecoverFlow | +₹367,743.11 | N/A (Theoretical Limit) | [+278,687.34, +460,644.17] |

## 3. Oracle Isolation Disclaimer
> [!IMPORTANT]
> **Evaluation-Only Theoretical Upper Bound**: The Oracle Policy evaluates true expected value using hidden simulator ground truth. It is **not deployable** and is **strictly isolated from production decision and policy modules** (`api/`, `policies/`). It serves exclusively as a benchmarking ceiling.

## 4. Per-Seed Breakdown (All 10 Benchmark Seeds)
| Seed | Fixed Schedule (INR) | Best Static (INR) | Heuristic (INR) | RecoverFlow (INR) | Oracle (INR) |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 42 | ₹8,707,889.33 | ₹9,222,718.15 | ₹9,274,467.14 | ₹9,338,564.07 | ₹9,750,131.75 |
| 101 | ₹8,662,030.31 | ₹9,091,628.81 | ₹9,244,349.58 | ₹9,460,914.58 | ₹9,779,851.51 |
| 2026 | ₹8,961,738.67 | ₹9,475,575.34 | ₹9,461,928.59 | ₹9,548,704.15 | ₹9,988,721.27 |
| 301 | ₹8,614,394.38 | ₹9,143,056.04 | ₹9,031,307.67 | ₹9,419,347.21 | ₹9,710,087.71 |
| 402 | ₹8,820,048.78 | ₹9,168,672.25 | ₹9,284,311.25 | ₹9,378,905.93 | ₹9,798,899.22 |
| 503 | ₹8,688,542.90 | ₹9,251,534.64 | ₹9,220,899.62 | ₹9,359,734.77 | ₹9,823,226.51 |
| 604 | ₹8,669,924.56 | ₹9,333,706.60 | ₹9,261,382.94 | ₹9,750,870.88 | ₹9,907,928.68 |
| 705 | ₹8,572,819.62 | ₹9,092,557.93 | ₹9,006,130.13 | ₹8,985,827.82 | ₹9,644,658.30 |
| 806 | ₹8,816,183.90 | ₹9,278,246.97 | ₹9,285,819.18 | ₹9,385,294.79 | ₹9,766,175.82 |
| 907 | ₹9,145,137.20 | ₹9,679,643.82 | ₹9,956,927.20 | ₹10,233,307.07 | ₹10,369,221.55 |