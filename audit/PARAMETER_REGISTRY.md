# 🛡️ RECOVERFLOW PARAMETER REGISTRY

> **Taxonomy and Classification of All RecoverFlow Parameters into Learned State, Policy Hyperparameters, and Business/Scenario Assumptions**

---

## 1. Parameter Taxonomy & Classification

The table below classifies every tunable parameter found across `policies/linucb.py`, `core/config.py`, `core/risk.py`, `core/strategy.py`, and `simulator/scenario_config.py` into exactly three mutually exclusive categories:

1. **`Learned State`**: Values that change automatically during execution from observed online feedback and transaction data.
2. **`Policy Hyperparameter`**: Fixed algorithmic constants that shape learning dynamics and stopping rules, set by developers rather than learned.
3. **`Business/Scenario Assumption`**: Operational parameters, monetary values, risk weights, friction profiles, and environmental scenario multipliers representing domain assumptions.

| Parameter Name | Location (file) | Category | Current Default Value | Purpose / Description |
| :--- | :--- | :--- | :--- | :--- |
| **`self.A`** | `policies/linucb.py` | Learned State | `np.eye(19)` per arm | Disjoint ridge regression precision matrix $A_a = \mathbf{I}_d + \sum x_i x_i^T$ updated online upon retry outcomes. |
| **`self.b`** | `policies/linucb.py` | Learned State | `np.zeros(19)` per arm | Disjoint response vector $b_a = \sum r_i x_i$ accumulated online from realized net rewards. |
| **`self.arm_pull_counts`** | `policies/linucb.py` | Learned State | `{arm: 0}` per arm | Incremental pull counter tracking evaluation sample size per arm for cold-start safeguards. |
| **`alpha`** | `policies/linucb.py` | Policy Hyperparameter | `1.0` | Exploration trade-off hyperparameter controlling LinUCB upper confidence bound width. |
| **`max_attempts`** | `policies/linucb.py` | Policy Hyperparameter | `4` | Maximum allowable retry attempts ceiling per transaction before hard termination. |
| **`stopping_mode`** | `policies/linucb.py` | Policy Hyperparameter | `"expected_value"` | Active stopping evaluation rule (`"expected_value"` or legacy `"tau_decay"`). |
| **`min_samples_for_stopping`** | `policies/linucb.py` | Policy Hyperparameter | `15` | Cold-start observation threshold required per arm before expected-value stopping rule can trigger. |
| **`soft_decay_base_threshold`** | `policies/linucb.py` | Policy Hyperparameter | `0.0` | Base expected net revenue threshold in INR for stopping continuation checks. |
| **`retry_cost`** | `policies/linucb.py` | Business/Scenario Assumption | `10.0` | Monetary cost penalty in INR incurred per retry attempt (imported from `DEFAULT_RETRY_COST`). |
| **`MIN_CONFIDENCE_SCALE`** | `core/config.py` | Business/Scenario Assumption | `50.0` | Minimum scale floor in INR used in relative gap calculation to prevent division-by-zero near zero UCB scores. |
| **`CONFIDENCE_GAP_NORM_FACTOR`** | `core/config.py` | Business/Scenario Assumption | `0.25` | Score gap normalization factor (25% relative gap yields 1.0 decision confidence). |
| **`STABLE_CONFIDENCE_THRESHOLD`** | `core/config.py` | Business/Scenario Assumption | `0.50` | Minimum confidence score threshold for `STABLE` decision stability classification. |
| **`MODERATE_CONFIDENCE_THRESHOLD`** | `core/config.py` | Business/Scenario Assumption | `0.20` | Minimum confidence score threshold for `MODERATELY_STABLE` decision stability classification. |
| **`ARM_RISK_PROFILE`** | `core/config.py` | Business/Scenario Assumption | `{"3d": 0.10, "1d": 0.25, "6hr": 0.45, "1hr": 0.70, "7d": 0.85}` | Dimensionless timing friction profile $R_a \in [0.0, 1.0]$ representing operational friction and churn risk. |
| **`EXTREME_ARM_FRICTION`** | `core/config.py` | Business/Scenario Assumption | `{"1hr": 0.35, "7d": 0.40}` | Dimensionless extreme delay window friction profile $E_a$ used in `CONSERVATIVE` mode. |
| **`DEFAULT_ARM_RISK`** | `core/config.py` | Business/Scenario Assumption | `0.25` | Fallback dimensionless timing friction value for unmapped retry arms. |
| **`BALANCED_RISK_WEIGHT`** | `core/config.py` | Business/Scenario Assumption | `0.30` | Risk weight multiplier $\lambda_{\text{bal}}$ controlling uncertainty-weighted friction in `BALANCED` mode. |
| **`CONSERVATIVE_RISK_WEIGHT`** | `core/config.py` | Business/Scenario Assumption | `0.70` | Risk weight multiplier $\lambda_{\text{cons}}$ controlling uncertainty-weighted friction in `CONSERVATIVE` mode. |
| **`CONSERVATIVE_EXTREME_WEIGHT`** | `core/config.py` | Business/Scenario Assumption | `0.50` | Extreme window friction weight multiplier $\mu_{\text{extreme}}$ in `CONSERVATIVE` mode. |
| **`UNCERTAINTY_RISK_WEIGHT`** | `core/config.py` | Business/Scenario Assumption | `0.35` | Multiplier controlling the contribution of score gap uncertainty $(1 - C)$ to context risk profiles. |
| **`LOW_RISK_THRESHOLD`** | `core/config.py` | Business/Scenario Assumption | `0.30` | Risk score upper bound threshold for `LOW` risk profile classification. |
| **`MEDIUM_RISK_THRESHOLD`** | `core/config.py` | Business/Scenario Assumption | `0.60` | Risk score upper bound threshold for `MEDIUM` risk profile classification. |
| **`ATTEMPT_RISK_STEP`** | `core/config.py` | Business/Scenario Assumption | `0.15` | Risk score increment per repeated attempt beyond initial payment failure. |
| **`MAX_ATTEMPT_RISK`** | `core/config.py` | Business/Scenario Assumption | `0.40` | Maximum cumulative risk score contribution cap from attempt counts. |
| **`HIGH_RISK_FAILURE_PENALTY`** | `core/config.py` | Business/Scenario Assumption | `0.25` | Risk score penalty addition for high-friction decline codes. |
| **`MEDIUM_RISK_FAILURE_PENALTY`** | `core/config.py` | Business/Scenario Assumption | `0.15` | Risk score penalty addition for medium-friction decline codes. |
| **`HIGH_RISK_FAILURE_CODES`** | `core/risk.py` | Business/Scenario Assumption | `{"do_not_honor", "card_expired"}` | Failure categories classified as high risk in contextual risk profiling. |
| **`MEDIUM_RISK_FAILURE_CODES`** | `core/risk.py` | Business/Scenario Assumption | `{"insufficient_funds", "generic_decline"}` | Failure categories classified as medium risk in contextual risk profiling. |
| **`MARGINAL_THETA_THRESHOLD`** | `core/config.py` | Business/Scenario Assumption | `25.0` | Net revenue threshold in INR below which recommended retries are flagged as marginal. |
| **`MARGINAL_IMPLIED_PROBABILITY_THRESHOLD`** | `core/config.py` | Business/Scenario Assumption | `3.0` | Implied recovery probability percentage below which retries are flagged as marginal. |
| **`DETERMINISTIC_ARM_ORDER`** | `core/config.py` | Business/Scenario Assumption | `["3d", "1d", "6hr", "1hr", "7d"]` | Default arm preference sequence used for explicit deterministic tie-breaking. |
| **`RETRY_ARM_TO_STRATEGY`** | `core/strategy.py` | Business/Scenario Assumption | `{"1hr": IMMEDIATE, "6hr": FAST, "1d": BALANCED, "3d": PATIENT, "7d": LAST_CHANCE}` | Mapping from retry delay arms to human-readable strategy categories. |
| **`BASELINE_SCENARIO`** | `simulator/scenario_config.py` | Business/Scenario Assumption | `recovery_mult=1.0, amount_mult=1.0, overrides=None` | Phase 4B reference scenario multipliers (neutral environment). |
| **`HIGH_INSUFFICIENT_FUNDS_SCENARIO`** | `simulator/scenario_config.py` | Business/Scenario Assumption | `overrides={"insufficient_funds": 0.60, ...}` | Phase 4B scenario weight overrides increasing NSF share to 60%. |
| **`DISTRIBUTION_SHIFT_SCENARIO`** | `simulator/scenario_config.py` | Business/Scenario Assumption | `recovery_mult=0.70, overrides={"issuer_timeout": 0.42, ...}` | Phase 4B stress scenario multipliers with 30% recovery drop and inverted failure mix. |

---

## 2. Integrity Disclosure Statement

This registry exists to make explicit which numbers in RecoverFlow are the output of learning versus deliberate engineering choices — no parameter in this system is presented as 'AI-learned' unless it is listed under Learned State above.
