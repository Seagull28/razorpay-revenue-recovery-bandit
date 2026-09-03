"""
config.py
Centralized Configuration & Strategy/Risk Constants for RecoverFlow.

Every constant here is explicitly classified:
- Numerical stability safeguard
- Domain assumption
- Design parameter
"""

from typing import Dict, List

# ==============================================================================
# 1. NUMERICAL STABILITY SAFEGUARDS
# ==============================================================================

MIN_CONFIDENCE_SCALE: float = 50.0
"""
Classification: Numerical stability safeguard.
Purpose: Sets a minimum scale floor (50.0 INR) for relative score gap confidence calculations
         to prevent division-by-zero or unstable normalization when top candidate UCB scores are near zero.
Valid Range: > 0.0 (default: 50.0 INR)
"""

# ==============================================================================
# 2. CONFIDENCE CALIBRATION CONSTANTS
# ==============================================================================

CONFIDENCE_GAP_NORM_FACTOR: float = 0.25
"""
Classification: Design parameter.
Purpose: Normalization factor for relative score gap confidence. A 25% relative gap between top two candidate
         arm UCB scores produces a 100% (1.0) decision confidence score.
Valid Range: 0.05 to 1.0 (default: 0.25)
"""

STABLE_CONFIDENCE_THRESHOLD: float = 0.50
"""
Classification: Design parameter.
Purpose: Minimum confidence score (0.50, corresponding to >= 12.5% relative score separation) required
         to classify a decision as 'STABLE'.
Valid Range: 0.0 to 1.0 (default: 0.50)
"""

MODERATE_CONFIDENCE_THRESHOLD: float = 0.20
"""
Classification: Design parameter.
Purpose: Minimum confidence score (0.20, corresponding to >= 5.0% relative score separation) required
         to classify a decision as 'MODERATELY_STABLE'. Scores below 0.20 are classified as 'UNSTABLE'.
Valid Range: 0.0 to STABLE_CONFIDENCE_THRESHOLD (default: 0.20)
"""

# ==============================================================================
# 3. DOMAIN-INFORMED ARM FRICTION & RISK PROFILES (DIMENSIONLESS)
# ==============================================================================

ARM_RISK_PROFILE: Dict[str, float] = {
    "3d": 0.10,  # Patient replenish window — lowest timing friction
    "1d": 0.25,  # Balanced daily processing window
    "6hr": 0.45, # Intraday retry — moderate congestion/timing friction
    "1hr": 0.70, # Immediate retry — high risk of retrying before bank/customer state changes
    "7d": 0.85,  # Extended 7-day window — high opportunity-cost & customer churn risk
}
"""
Classification: Domain assumption.
Purpose: Dimensionless friction values R_a in [0.0, 1.0] representing operational timing friction,
         customer interruption, and churn risk associated with each retry delay window.
"""

EXTREME_ARM_FRICTION: Dict[str, float] = {
    "1hr": 0.35, # High operational volatility (immediate retry before status resolution)
    "7d": 0.40,  # High customer churn exposure / extended window opportunity cost
}
"""
Classification: Domain assumption.
Purpose: Additional dimensionless friction values E_a for extreme delay windows (1hr, 7d) used in Conservative mode.
"""

DEFAULT_ARM_RISK: float = 0.25
"""
Classification: Fallback default.
Purpose: Fallback dimensionless timing friction value for unmapped retry delay arms.
"""

# ==============================================================================
# 4. STRATEGY MODE RISK WEIGHTS (DESIGN PARAMETERS)
# ==============================================================================

BALANCED_RISK_WEIGHT: float = 0.30
"""
Classification: Design parameter.
Purpose: Multiplier lambda_bal controlling the strength of uncertainty-weighted arm timing friction in BALANCED mode.
Valid Range: 0.0 to 1.0 (default: 0.30)
"""

CONSERVATIVE_RISK_WEIGHT: float = 0.70
"""
Classification: Design parameter.
Purpose: Multiplier lambda_cons controlling the strength of uncertainty-weighted arm timing friction in CONSERVATIVE mode.
Valid Range: BALANCED_RISK_WEIGHT to 1.0 (default: 0.70)
"""

CONSERVATIVE_EXTREME_WEIGHT: float = 0.50
"""
Classification: Design parameter.
Purpose: Multiplier mu_extreme controlling extreme window friction in CONSERVATIVE mode.
Valid Range: 0.0 to 1.0 (default: 0.50)
"""

# ==============================================================================
# 5. CONTEXTUAL RISK PROFILE COMPONENTS
# ==============================================================================

UNCERTAINTY_RISK_WEIGHT: float = 0.35
"""
Classification: Design parameter.
Purpose: Multiplier controlling the contribution of decision score gap uncertainty (1 - C) to the context risk score.
Valid Range: 0.0 to 1.0 (default: 0.35)
"""

LOW_RISK_THRESHOLD: float = 0.30
"""
Classification: Risk threshold.
Purpose: Upper bound risk score threshold for LOW risk classification.
"""

MEDIUM_RISK_THRESHOLD: float = 0.60
"""
Classification: Risk threshold.
Purpose: Upper bound risk score threshold for MEDIUM risk classification. Scores >= 0.60 are classified as HIGH risk.
"""

ATTEMPT_RISK_STEP: float = 0.15
"""
Classification: Domain assumption.
Purpose: Risk score increment per repeated attempt beyond initial payment failure.
"""

MAX_ATTEMPT_RISK: float = 0.40
"""
Classification: Numerical stability safeguard / cap.
Purpose: Maximum cumulative risk score contribution from attempt counts.
"""

HIGH_RISK_FAILURE_PENALTY: float = 0.25
"""
Classification: Domain assumption.
Purpose: Base risk score addition for high-friction failure codes ('do_not_honor', 'card_expired').
"""

MEDIUM_RISK_FAILURE_PENALTY: float = 0.15
"""
Classification: Domain assumption.
Purpose: Base risk score addition for medium-friction failure codes ('insufficient_funds', 'generic_decline').
"""

# ==============================================================================
# 6. EXPLAINABILITY & HEURISTIC THRESHOLDS
# ==============================================================================

MARGINAL_THETA_THRESHOLD: float = 25.0
"""
Classification: Design parameter.
Purpose: Expected net revenue threshold in INR below which a recommended retry decision is flagged as marginal.
"""

MARGINAL_IMPLIED_PROBABILITY_THRESHOLD: float = 3.0
"""
Classification: Design parameter.
Purpose: Model-implied recovery probability percentage below which a recommended retry decision is flagged as marginal.
"""

DETERMINISTIC_ARM_ORDER: List[str] = ["3d", "1d", "6hr", "1hr", "7d"]
"""
Classification: Design parameter.
Purpose: Default arm preference sequence used for explicit deterministic tie-breaking.
"""
