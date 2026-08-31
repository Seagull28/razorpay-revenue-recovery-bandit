import sys
from pathlib import Path
import os
import shutil

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.evaluation.harness import EvaluationHarness
from bandit_retry_scheduler.evaluation.plotting import plot_cold_start_comparison

def main():
    harness = EvaluationHarness(seeds=[42], num_days=30, transactions_per_day=100)
    seed_res = harness.run_seed_benchmark(42)
    
    cold_overall = seed_res["cold_start_data"]
    cold_timeout = seed_res["cold_start_timeout_data"]
    
    audit_plot_path = r"C:\Users\Thanujha\.gemini\antigravity\scratch\bandit_retry_scheduler\audit\plots\cold_start_comparison.png"
    brain_plot_path = r"C:\Users\Thanujha\.gemini\antigravity\brain\30eeb98e-59ae-47b5-85ad-a23d7f580f5a\plots\cold_start_comparison.png"
    
    print("Generating 2x2 cold start comparison plot...")
    plot_cold_start_comparison(cold_overall, cold_timeout, audit_plot_path)
    shutil.copy(audit_plot_path, brain_plot_path)
    
    print(f"Audit plot size: {os.path.getsize(audit_plot_path)} bytes")
    print(f"Brain plot size: {os.path.getsize(brain_plot_path)} bytes")
    print("Plot regenerated successfully!")

if __name__ == "__main__":
    main()
