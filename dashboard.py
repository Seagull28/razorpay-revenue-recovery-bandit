"""
dashboard.py
RecoverFlow Interactive Merchant Dashboard (Streamlit).
Combines Overview Metrics (Page 1) and Live Decision Walkthrough (Section A).
Uses live API calls from api/ decision_service, eligibility, explainability, action_executor, feedback_loop.
"""

import sys
from pathlib import Path
import streamlit as st
import pandas as pd
import numpy as np

# Append project root
sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.simulator.environment import RetrySimulator
from bandit_retry_scheduler.simulator.config import FailureCode, Bank, Network, DelayArm
from bandit_retry_scheduler.api.eligibility import check_eligibility
from bandit_retry_scheduler.api.decision_service import get_retry_decision
from bandit_retry_scheduler.api.explainability import generate_decision_explanation
from bandit_retry_scheduler.api.action_executor import execute_retry_action
from bandit_retry_scheduler.api.feedback_loop import process_outcome_and_update
from bandit_retry_scheduler.audit.logger import AuditLogger

# Page configuration
st.set_page_config(
    page_title="RecoverFlow Merchant Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for styling
st.markdown("""
<style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 16px;
        border-left: 5px solid #1f77b4;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .eligible-banner {
        background-color: #d4edda;
        color: #155724;
        padding: 12px 18px;
        border-radius: 6px;
        border: 1px solid #c3e6cb;
        font-weight: 600;
        font-size: 15px;
        margin-bottom: 15px;
    }
    .ineligible-banner {
        background-color: #f8d7da;
        color: #721c24;
        padding: 12px 18px;
        border-radius: 6px;
        border: 1px solid #f5c6cb;
        font-weight: 600;
        font-size: 15px;
        margin-bottom: 15px;
    }
    .highlight-row {
        background-color: #e8f4f8 !important;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator

@st.cache_resource
def load_pretrained_policy_and_simulator(num_tx: int = 1000):
    """Pre-trains LinUCB policy on 1,000 transactions matching Seed 42 stream for realistic arm scoring."""
    policy = LinUCBPolicy(min_samples_for_stopping=15)
    simulator = RetrySimulator(seed=42)
    stream_gen = TransactionStreamGenerator(seed=42)
    num_days = max(1, num_tx // 100)
    engine = PolicyExecutionEngine(simulator=simulator)
    stream = stream_gen.generate_stream(num_days=num_days, transactions_per_day=100)
    engine.run(stream, policy=policy, logger=AuditLogger())
    return policy, simulator

# Initialize persistent session state for Policy, Simulator, and Audit Logger
if "policy" not in st.session_state:
    p_init, s_init = load_pretrained_policy_and_simulator(1000)
    st.session_state.policy = p_init
    st.session_state.simulator = s_init

if "audit_logger" not in st.session_state:
    st.session_state.audit_logger = AuditLogger()


# Header Banner
st.title("⚡ RecoverFlow: Bandit-Optimized Retry Scheduler")
st.markdown("**Production Merchant Performance & Live Policy Walkthrough**")
st.markdown("---")

# =============================================================================
# SECTION 1: OVERVIEW METRICS & BENCHMARKS (PAGE 1)
# =============================================================================
st.header("📊 Section 1: Executive Overview & Multi-Seed Benchmarks")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="Baseline Net Revenue",
        value="INR 65,28,431.32",
        help="Fixed-schedule baseline (1d -> 3d -> 7d) on Seed 42",
    )

with col2:
    st.metric(
        label="LinUCB Net Revenue",
        value="INR 79,98,301.40",
        delta="+INR 14,69,870.08 (+22.51%)",
        help="Canonical LinUCB Policy Net Revenue on Seed 42",
    )

with col3:
    st.metric(
        label="10-Seed Mean Net Lift",
        value="+15.34%",
        delta="95% CI: [+11.50%, +18.86%]",
        help="Mean lift across 10 random seeds with 10,000 bootstrap CI",
    )

with col4:
    st.metric(
        label="Canonical Recovery Rate",
        value="66.20%",
        delta="+14.03% vs Baseline (52.17%)",
        help="Seed 42 overall transaction recovery rate",
    )

st.markdown("### Per-Failure-Code Performance Breakdown (Seed 42)")

# Pre-computed Seed 42 benchmark dataframe directly matching evaluation_report.md
code_data = [
    {"Failure Code": "card_expired", "Baseline Net (INR)": -2450.00, "LinUCB Net (INR)": -2450.00, "Lift (INR)": 0.00, "Lift (%)": "0.00%", "Recovery Rate": "0.00%"},
    {"Failure Code": "do_not_honor", "Baseline Net (INR)": 342808.17, "LinUCB Net (INR)": 495011.64, "Lift (INR)": 152203.47, "Lift (%)": "+44.40%", "Recovery Rate": "19.52%"},
    {"Failure Code": "generic_decline", "Baseline Net (INR)": 525991.02, "LinUCB Net (INR)": 568369.17, "Lift (INR)": 42378.15, "Lift (%)": "+8.06%", "Recovery Rate": "57.01%"},
    {"Failure Code": "insufficient_funds", "Baseline Net (INR)": 5016138.31, "LinUCB Net (INR)": 5776351.11, "Lift (INR)": 760212.80, "Lift (%)": "+15.16%", "Recovery Rate": "81.49%"},
    {"Failure Code": "issuer_timeout", "Baseline Net (INR)": 645943.82, "LinUCB Net (INR)": 1161019.48, "Lift (INR)": 515075.66, "Lift (%)": "+79.74%", "Recovery Rate": "93.15%"},
]

df_code = pd.DataFrame(code_data)
st.dataframe(df_code, use_container_width=True, hide_index=True)

st.markdown("---")

# =============================================================================
# SECTION A: LIVE DECISION WALKTHROUGH
# =============================================================================
st.header("🔍 Section A: Live Decision Walkthrough & Action Execution")
st.markdown("Select a sample transaction context below to inspect live LinUCB eligibility, arm scoring, plain-language business explanations, and test action execution against the environment.")

# Pre-loaded transaction options
preset_txs = {
    "Insufficient Funds (High-Ticket, Bank B)": {
        "transaction_id": "tx_demo_insufficient_funds_001",
        "amount": 5000.0,
        "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
        "bank": Bank.BANK_B.value,
        "network": Network.VISA.value,
        "customer_prior_success_count": "4+",
        "customer_prior_failures_this_cycle": "0",
        "day_of_month_bucket": "salary_cycle",
        "attempt_number": 1,
    },
    "Issuer Timeout (Standard, Bank C)": {
        "transaction_id": "tx_demo_issuer_timeout_002",
        "amount": 1500.0,
        "failure_code": FailureCode.ISSUER_TIMEOUT.value,
        "bank": Bank.BANK_C.value,
        "network": Network.MASTERCARD.value,
        "customer_prior_success_count": "1-3",
        "customer_prior_failures_this_cycle": "0",
        "day_of_month_bucket": "early",
        "attempt_number": 1,
    },
    "Do Not Honor (High-Ticket, Bank A)": {
        "transaction_id": "tx_demo_do_not_honor_003",
        "amount": 4500.0,
        "failure_code": FailureCode.DO_NOT_HONOR.value,
        "bank": Bank.BANK_A.value,
        "network": Network.RUPAY.value,
        "customer_prior_success_count": "0",
        "customer_prior_failures_this_cycle": "1",
        "day_of_month_bucket": "mid",
        "attempt_number": 1,
    },
    "Card Expired (Unrecoverable Hard Stop, Bank D)": {
        "transaction_id": "tx_demo_card_expired_004",
        "amount": 2000.0,
        "failure_code": FailureCode.CARD_EXPIRED.value,
        "bank": Bank.BANK_D.value,
        "network": Network.VISA.value,
        "customer_prior_success_count": "1-3",
        "customer_prior_failures_this_cycle": "1",
        "day_of_month_bucket": "mid",
        "attempt_number": 2,
    },
    "Generic Decline (Standard, Bank A)": {
        "transaction_id": "tx_demo_generic_decline_005",
        "amount": 1200.0,
        "failure_code": FailureCode.GENERIC_DECLINE.value,
        "bank": Bank.BANK_A.value,
        "network": Network.MASTERCARD.value,
        "customer_prior_success_count": "4+",
        "customer_prior_failures_this_cycle": "0",
        "day_of_month_bucket": "late",
        "attempt_number": 1,
    },
    "Custom Transaction Entry": "custom",
}

selected_preset = st.selectbox(
    "📌 Select Sample Transaction Context:",
    options=list(preset_txs.keys()),
    index=0,
)

if selected_preset == "Custom Transaction Entry":
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        custom_fc = st.selectbox("Failure Code", options=[fc.value for fc in FailureCode])
        custom_amount = st.number_input("Amount (INR)", min_value=100.0, max_value=50000.0, value=2500.0)
    with c2:
        custom_bank = st.selectbox("Issuing Bank", options=[b.value for b in Bank])
        custom_attempt = st.number_input("Attempt Number", min_value=1, max_value=4, value=1)
    with c3:
        custom_network = st.selectbox("Card Network", options=[n.value for n in Network])
        custom_bucket = st.selectbox("Day of Month Bucket", options=["early", "mid", "late", "salary_cycle"])
    with c4:
        custom_priors = st.selectbox("Customer Prior Successes", options=["0", "1-3", "4+"])
        custom_fails = st.selectbox("Prior Failures in Cycle", options=["0", "1", "2+"])

    tx_context = {
        "transaction_id": "tx_demo_custom",
        "amount": float(custom_amount),
        "failure_code": custom_fc,
        "bank": custom_bank,
        "network": custom_network,
        "customer_prior_success_count": custom_priors,
        "customer_prior_failures_this_cycle": custom_fails,
        "day_of_month_bucket": custom_bucket,
        "attempt_number": int(custom_attempt),
    }
else:
    tx_context = dict(preset_txs[selected_preset])

attempt_num = tx_context.get("attempt_number", 1)

# 1. LIVE ELIGIBILITY GATE CHECK
is_eligible, eligibility_reason = check_eligibility(
    transaction=tx_context,
    attempt_number=attempt_num,
)

if is_eligible:
    st.markdown(
        f'<div class="eligible-banner">✅ <b>ELIGIBLE FOR RETRY</b> — Attempt {attempt_num} | Context Status: {eligibility_reason}</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<div class="ineligible-banner">❌ <b>INELIGIBLE FOR RETRY (HALTED)</b> — Attempt {attempt_num} | Reason: {eligibility_reason}</div>',
        unsafe_allow_html=True,
    )

# 2. LIVE DECISION SERVICE CALL
decision = get_retry_decision(
    transaction=tx_context,
    policy=st.session_state.policy,
    attempt_number=attempt_num,
)

# 3. ARM SCORES COMPARISON TABLE
st.markdown("#### 🎯 Bandit 5-Arm Point Estimates & Upper Confidence Bounds")

rec_delay = decision.get("recommended_delay")
arm_scores = decision.get("arm_scores", {})

table_rows = []
for arm_name in ["1hr", "6hr", "1d", "3d", "7d"]:
    info = arm_scores.get(arm_name, {"theta_dot_x": 0.0, "bonus": 0.0, "ucb_score": 0.0, "pull_count": 0})
    is_recommended = (arm_name == rec_delay and decision["should_retry"])
    
    table_rows.append({
        "Status": "⭐ RECOMMENDED" if is_recommended else "",
        "Delay Arm": arm_name,
        "Point Estimate θ^T x (INR)": f"₹{info['theta_dot_x']:,.2f}",
        "Exploration Bonus (INR)": f"₹{info['bonus']:,.2f}",
        "Combined UCB Score (INR)": f"₹{info['ucb_score']:,.2f}",
        "Historical Pull Count": info["pull_count"],
    })

df_arms = pd.DataFrame(table_rows)

# Highlight recommended row using pandas styling
def highlight_rec(row):
    if "RECOMMENDED" in str(row["Status"]):
        return ["background-color: #d1ecf1; font-weight: bold; color: #0c5460;"] * len(row)
    return [""] * len(row)

st.dataframe(
    df_arms.style.apply(highlight_rec, axis=1),
    use_container_width=True,
    hide_index=True,
)

# 4. PLAIN LANGUAGE BUSINESS EXPLANATION
st.markdown("#### 💡 Decision Rationale & Business Explanation")
st.info(decision["explanation"])

# 5. LIVE ACTION EXECUTION & ONLINE FEEDBACK LOOP BUTTON
st.markdown("#### 🚀 Action Execution & Online Learning Feedback Loop")

btn_col, info_col = st.columns([1, 2])

with btn_col:
    execute_clicked = st.button("▶ Execute Retry Action", type="primary", use_container_width=True)

if execute_clicked:
    # Capture BEFORE state for chosen arm
    chosen_arm = decision["recommended_delay"] if decision["should_retry"] else "1hr"
    before_info = arm_scores.get(chosen_arm, {"pull_count": 0, "theta_dot_x": 0.0})
    before_pulls = before_info["pull_count"]
    before_theta = before_info["theta_dot_x"]

    # Execute action against simulator
    exec_result = execute_retry_action(
        transaction=tx_context,
        decision=decision,
        simulator=st.session_state.simulator,
    )

    # Process feedback and update policy parameters online
    update_record = process_outcome_and_update(
        transaction=tx_context,
        decision=decision,
        execution_result=exec_result,
        policy=st.session_state.policy,
        audit_logger=st.session_state.audit_logger,
    )

    # Capture AFTER state for chosen arm
    after_scores = st.session_state.policy.get_arm_scores(tx_context)
    after_info = after_scores.get(chosen_arm, {"pull_count": 0, "theta_dot_x": 0.0})
    after_pulls = after_info["pull_count"]
    after_theta = after_info["theta_dot_x"]

    with info_col:
        st.success(
            f"**Action Executed**: `{exec_result['action_taken']}` | "
            f"**Outcome**: `{exec_result['outcome']}` | "
            f"**Recovered**: `INR {exec_result['amount_recovered']:,.2f}` | "
            f"**Net Reward**: `INR {exec_result['reward']:,.2f}`"
        )
        st.markdown(
            f"**Online Model Parameter Update (`{chosen_arm}` arm)**:\n"
            f"- **Pull Count**: `{before_pulls}` ➔ `{after_pulls}` (+1 pull)\n"
            f"- **Point Estimate $\\hat{{\\theta}}^T \\mathbf{{x}}$**: `INR {before_theta:,.2f}` ➔ `INR {after_theta:,.2f}`"
        )

# =============================================================================
# SECTION C: LEARNING INSIGHTS & EMPIRICAL EVIDENCE CARDS
# =============================================================================
st.markdown("---")
st.header("📈 Section C: Algorithmic Learning Insights & Empirical Evidence")
st.markdown("Key structural findings from canonical evaluation (Seed 42 & 10-Seed Benchmark), paired directly with pre-rendered empirical plot evidence.")

card_col1, card_col2 = st.columns(2)

with card_col1:
    st.subheader("1. `issuer_timeout` Convergence")
    st.markdown("""
    **Headline**: `issuer_timeout` on Bank C converges rapidly to `1hr`
    
    **Empirical Findings**:
    - Ground-truth optimal arm is `1hr` (78% base recovery probability).
    - The LinUCB bandit reaches 100% selection share on `1hr` delay.
    - Recovery rate improved from **53.15%** (Baseline) to **93.15%** (LinUCB), generating a **+79.74%** net revenue lift (+INR 5,15,075.66).
    """)
    convergence_img_path = Path(r"C:\Users\Thanujha\.gemini\antigravity\scratch\bandit_retry_scheduler\audit\plots\convergence_plots.png")
    if convergence_img_path.exists():
        st.image(str(convergence_img_path), caption="Figure 1: Arm Selection Convergence Across 40-Decision Rolling Windows", use_container_width=True)

with card_col2:
    st.subheader("2. `insufficient_funds` Zero-Shot Generalization")
    st.markdown("""
    **Headline**: `insufficient_funds` generalizes to `3d` across all four banks
    
    **Empirical Findings**:
    - `3d` delay is the ground-truth optimal arm for all 4 banks (Bank A: 40%, Bank B: 45%, Bank C: 38%, Bank D: 42%).
    - Because `failure_code` is a shared linear feature in the disjoint LinUCB 19D encoder, the model transferred learned arm preferences to new banks zero-shot without needing separate exploration.
    - Yields net revenue lift of **+15.16%** (+INR 7,60,212.80) on Seed 42.
    """)

st.markdown("")
card_col3, card_col4 = st.columns(2)

with card_col3:
    st.subheader("3. Bank D Drift Adaptation")
    st.markdown("""
    **Headline**: Bank D policy drift on Day 20 — bandit adapts without retraining
    
    **Empirical Findings**:
    - Bank D undergoes policy drift on Day 20 (`do_not_honor` recovery rate jumps from 3.57% to 82.14%).
    - LinUCB automatically detects shifted reward distribution, increasing recovery rate from **3.57%** pre-drift to **82.14%** post-drift.
    - Arm allocation shifts seamlessly from exploration to heavily favoring `1d`/`3d` without manual model retraining.
    """)
    drift_img_path = Path(r"C:\Users\Thanujha\.gemini\antigravity\scratch\bandit_retry_scheduler\audit\plots\drift_adaptation.png")
    if drift_img_path.exists():
        st.image(str(drift_img_path), caption="Figure 2: Bank D Rolling 40-Decision Arm Selection Distribution Pre/Post Drift", use_container_width=True)

with card_col4:
    st.subheader("4. Adaptive Threshold Experiment")
    st.markdown("""
    **Headline**: Tested per-segment adaptive stopping thresholds — and correctly rejected it
    
    **Empirical Findings**:
    - Evaluated raising `min_samples_for_stopping` from 15 to 25 for high-ticket failure codes (`insufficient_funds`, `do_not_honor`).
    - Forced extra exploration on non-viable arms reduced overall net revenue by **-1.63% (-INR 1,30,473.19)**.
    - Retained the canonical `min_samples=15` configuration based on rigorous empirical evidence.
    """)
