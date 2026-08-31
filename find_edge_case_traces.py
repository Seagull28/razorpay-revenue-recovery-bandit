import sys
import os
import numpy as np

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.runner.engine import PolicyExecutionEngine
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator
from bandit_retry_scheduler.policies.linucb import LinUCBPolicy

class TracingLinUCBPolicy(LinUCBPolicy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trace_1_found = False
        self.trace_2_found = False

    def should_stop(self, context, attempt_number, previous_success=False):
        if attempt_number >= 4:
            return super().should_stop(context, attempt_number, previous_success)

        x = self.encoder.encode(context)
        point_estimates = {}
        for a in self.arms:
            theta_a = np.linalg.solve(self.A[a], self.b[a])
            point_estimates[a] = np.dot(theta_a, x)

        max_ev = max(point_estimates.values())
        min_pulls = min(self.arm_pull_counts.values())

        # Check for Trace 1: Cold start safeguard triggered
        if not self.trace_1_found and attempt_number >= 2:
            if min_pulls < self.min_samples_for_stopping and max_ev <= 0.0:
                print(f"=== TRACE 1: COLD START SAFEGUARD ===")
                print(f"Transaction ID: {context['transaction_id']}")
                print(f"Attempt Number: {attempt_number}")
                print(f"Arm Pulls (Global): {self.arm_pull_counts}")
                print(f"Point Estimates (Expected Value theta_a^T x):")
                best_arm = None
                best_ev = -float('inf')
                for a, ev in point_estimates.items():
                    print(f"  Arm {a} ({a}d delay): Rs {ev:.2f}")
                    if ev > best_ev:
                        best_ev = ev
                        best_arm = a
                print(f"Max EV: Rs {max_ev:.2f} (from Arm {best_arm})")
                print(f"Condition: Max EV <= 0 (raw estimate suggests STOP)")
                print(f"Safeguard Active: min_pulls ({min_pulls}) < min_samples_for_stopping ({self.min_samples_for_stopping})")
                print(f"Policy Action: FORCED CONTINUE")
                print("=====================================\n")
                self.trace_1_found = True

        # Check for Trace 2: Boundary case (-5 to +5 EV)
        if not self.trace_2_found and attempt_number >= 2:
            if min_pulls >= self.min_samples_for_stopping and -5.0 <= max_ev <= 5.0:
                print(f"=== TRACE 2: MATURE BOUNDARY CASE ===")
                print(f"Transaction ID: {context['transaction_id']}")
                print(f"Attempt Number: {attempt_number}")
                print(f"Arm Pulls (Global): {self.arm_pull_counts}")
                print(f"Point Estimates (Expected Value theta_a^T x):")
                best_arm = None
                best_ev = -float('inf')
                for a, ev in point_estimates.items():
                    print(f"  Arm {a} ({a}d delay): Rs {ev:.2f}")
                    if ev > best_ev:
                        best_ev = ev
                        best_arm = a
                print(f"Max EV: Rs {max_ev:.2f} (from Arm {best_arm})")
                action = "STOP (Negative EV)" if max_ev <= 0.0 else "CONTINUE (Positive EV)"
                print(f"Condition: min_pulls ({min_pulls}) >= min_samples_for_stopping ({self.min_samples_for_stopping})")
                print(f"Policy Action: {action}")
                print("=====================================\n")
                self.trace_2_found = True

        return super().should_stop(context, attempt_number, previous_success)

if __name__ == "__main__":
    generator = TransactionStreamGenerator(seed=42)
    transactions = generator.generate_stream(num_days=30, transactions_per_day=100)
    policy = TracingLinUCBPolicy(
        alpha=1.0,
        min_samples_for_stopping=15
    )
    engine = PolicyExecutionEngine()
    engine.run(transactions, policy)
    print("Simulation complete.")
    if not policy.trace_1_found:
        print("WARNING: Trace 1 not found.")
    if not policy.trace_2_found:
        print("WARNING: Trace 2 not found.")
