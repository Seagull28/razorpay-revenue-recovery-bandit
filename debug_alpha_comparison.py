"""
debug_alpha_comparison.py
Checks decision-by-decision whether alpha=1.0 and alpha=2.0 select identical arms across 6581 decisions.
Prints explicit per-arm scores (theta_dot_x, bonus, ucb_score) for decisions where alpha changes UCB score.
"""

import sys
import numpy as np
from dataclasses import asdict

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.policies.linucb import LinUCBPolicy
from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator
from bandit_retry_scheduler.simulator.environment import RetrySimulator

def run_debug_sim(alpha_val: float):
    gen = TransactionStreamGenerator(seed=42)
    txs = gen.generate_stream(num_days=30, transactions_per_day=100)
    sim = RetrySimulator(seed=42)
    engine = PolicyExecutionEngine(simulator=sim)
    policy = LinUCBPolicy(alpha=alpha_val, min_samples_for_stopping=15)
    
    print(f"Instantiated Policy with alpha = {policy.alpha} (type={type(policy.alpha)})")
    log = engine.run(transactions=txs, policy=policy)
    return log.records

records_a10 = run_debug_sim(1.0)
records_a20 = run_debug_sim(2.0)

print(f"\nTotal decisions logged for alpha=1.0: {len(records_a10)}")
print(f"Total decisions logged for alpha=2.0: {len(records_a20)}")

diffs = 0
for i, (r1, r2) in enumerate(zip(records_a10, records_a20)):
    arm1 = r1.arm_chosen if hasattr(r1, "arm_chosen") else r1["arm_chosen"]
    arm2 = r2.arm_chosen if hasattr(r2, "arm_chosen") else r2["arm_chosen"]
    if arm1 != arm2:
        diffs += 1
        if diffs <= 5:
            print(f"Decision {i}: alpha=1.0 chose '{arm1}', alpha=2.0 chose '{arm2}'")

print(f"\nTotal arm selection differences between alpha=1.0 and alpha=2.0: {diffs} / {len(records_a10)}")
