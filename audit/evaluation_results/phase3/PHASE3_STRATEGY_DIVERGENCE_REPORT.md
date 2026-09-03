# 🎯 RecoverFlow Strategy Mode Divergence Analysis Report

> **Empirical Validation of Strategy Mode Behavior under Score Gap Uncertainty**

---

## 📌 Executive Summary
This report presents targeted empirical validation proving that RecoverFlow strategy modes:
1. **Converge naturally** when decision confidence is high (clear score separation).
2. **Diverge appropriately** when decision confidence is low (narrow score gaps), shifting recommendations to lower-risk timing windows.

---

## 📊 Targeted Decision Scenario Results

| Scenario | Decision Confidence | Maximize Recovery | Balanced | Conservative | Mode Divergence? |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Scenario A: Clear Dominant Winner (High Confidence) | `1.0000` | `3d` | `3d` | `3d` | False |
| Scenario B: Close Competition with Uncertainty | `0.0400` | `1hr` | `3d` | `3d` | **TRUE** |
| Scenario C: High-Risk Extreme Arm vs Safer Arm | `0.1143` | `1hr` | `3d` | `3d` | **TRUE** |
| Scenario D: Low Confidence / Nearly Tied Scores | `0.0160` | `7d` | `3d` | `3d` | **TRUE** |
| Scenario E: Dominant Patient Arm (Perfect Confidence) | `1.0000` | `3d` | `3d` | `3d` | False |

---

## 💡 Key Empirical Findings
- **High Confidence Scenarios (A & E)**: Zero mode divergence (`Max = Bal = Cons = 3d`). Risk adjustments decay naturally as confidence approaches 1.0.
- **Uncertain / Narrow Gap Scenarios (B, C & D)**: Modes diverge legitimately. `MAXIMIZE_RECOVERY` selects the raw highest score (`1hr` or `7d`), `BALANCED` shifts to `3d`, and `CONSERVATIVE` shifts to `3d` (lowest timing friction).
