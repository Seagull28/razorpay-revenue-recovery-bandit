"""
inspect_ucb_gap.py
Inspects the per-arm point estimate (theta_dot_x) and exploration bonus (bonus)
across decision steps to explain why alpha=1.0 and alpha=2.0 yield identical arm choices.
"""

import sys
import numpy as np

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator

gen = TransactionStreamGenerator(seed=42)
txs = gen.generate_stream(num_days=30, transactions_per_day=100)

p1 = LinUCBPolicy(alpha=1.0)
p2 = LinUCBPolicy(alpha=2.0)

print("--- DECISION STEP PER-ARM SCORE COMPARISON (ALPHA=1.0 vs ALPHA=2.0) ---")

for step, tx in enumerate(txs[:10]): # check first 10 decisions
    scores1 = p1.get_arm_scores(tx)
    scores2 = p2.get_arm_scores(tx)
    
    print(f"\nDecision Step {step+1} [Tx {tx['transaction_id']}]:")
    print(f"  {'Arm':<6} | {'theta_dot_x':<12} | {'bonus (a=1)':<12} | {'UCB (a=1)':<12} | {'bonus (a=2)':<12} | {'UCB (a=2)':<12}")
    print("  " + "-"*75)
    for arm in p1.arms:
        s1 = scores1[arm]
        s2 = scores2[arm]
        print(f"  {arm:<6} | {s1['theta_dot_x']:12.2f} | {s1['bonus']:12.2f} | {s1['ucb_score']:12.2f} | {s2['bonus']:12.2f} | {s2['ucb_score']:12.2f}")
    
    # Update policies with simulated reward for chosen arm
    arm1 = p1.select_arm(tx, 1).arm_chosen
    arm2 = p2.select_arm(tx, 1).arm_chosen
    reward = 1000.0  # arbitrary reward for step inspection
    p1.update(tx, arm1, reward)
    p2.update(tx, arm2, reward)
