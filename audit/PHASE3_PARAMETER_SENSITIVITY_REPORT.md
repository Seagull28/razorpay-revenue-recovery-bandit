# 🔬 RecoverFlow Phase 3 Parameter Sensitivity & Calibration Report

> **Deterministic Parameter Sensitivity & Policy Assumption Calibration Analysis**

---

## 📌 Executive Summary
This report documents the sensitivity of RecoverFlow strategy mode recommendations across variations in risk weight parameters (lambda_bal, lambda_cons).

---

## 📊 Balanced Mode Risk Weight Sensitivity (lambda_bal)

| Risk Weight (lambda_bal) | Strategy Overrides | Override Rate (%) | Arm Distribution |
| :---: | :---: | :---: | :--- |
| `0.20` | `0` | `0.00%` | 1d: 153, 7d: 166, 1hr: 155, 3d: 15, 6hr: 11 |
| `0.30` | `6` | `1.20%` | 1d: 155, 7d: 162, 1hr: 155, 3d: 17, 6hr: 11 |
| `0.40` | `9` | `1.80%` | 1d: 158, 7d: 162, 1hr: 152, 3d: 17, 6hr: 11 |

---

## 📊 Conservative Mode Risk Weight Sensitivity (lambda_cons)

| Risk Weight (lambda_cons) | Strategy Overrides | Override Rate (%) | Arm Distribution |
| :---: | :---: | :---: | :--- |
| `0.60` | `17` | `3.40%` | 1d: 165, 7d: 159, 1hr: 147, 3d: 18, 6hr: 11 |
| `0.70` | `17` | `3.40%` | 1d: 165, 7d: 159, 1hr: 147, 3d: 18, 6hr: 11 |
| `0.80` | `18` | `3.60%` | 1d: 166, 7d: 158, 1hr: 147, 3d: 18, 6hr: 11 |

---

## 🔒 Policy Parameter Calibration Disclosure
Phase 3 strategy parameters are explicit product-policy design assumptions used to represent merchant risk preferences. They are **not learned from real merchant payment data**. In a production deployment, these parameters would be calibrated using historical retry outcomes, merchant preference profiles, recovery economics, and controlled experimentation.
