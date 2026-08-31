import os
import shutil
import time
from pathlib import Path
import sys

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.evaluation.harness import EvaluationHarness
from bandit_retry_scheduler.evaluation.plotting import plot_cold_start_comparison

def main():
    scratch_plot_dir = Path(r"C:\Users\Thanujha\.gemini\antigravity\scratch\bandit_retry_scheduler\audit\plots")
    brain_plot_dir = Path(r"C:\Users\Thanujha\.gemini\antigravity\brain\30eeb98e-59ae-47b5-85ad-a23d7f580f5a\plots")
    
    scratch_plot_dir.mkdir(parents=True, exist_ok=True)
    brain_plot_dir.mkdir(parents=True, exist_ok=True)

    harness = EvaluationHarness(seeds=[42], num_days=30, transactions_per_day=100)
    seed_res = harness.run_seed_benchmark(42)
    cold_overall = seed_res["cold_start_data"]
    cold_timeout = seed_res["cold_start_timeout_data"]

    # Save to fresh filenames to eliminate browser/UI caching
    filenames = ["cold_start_comparison.png", "cold_start_decomposed_2x2.png"]
    
    for filename in filenames:
        scratch_path = scratch_plot_dir / filename
        brain_path = brain_plot_dir / filename
        
        plot_cold_start_comparison(cold_overall, cold_timeout, str(scratch_path))
        shutil.copy(scratch_path, brain_path)
        
        mtime = time.ctime(os.path.getmtime(brain_path))
        size = os.path.getsize(brain_path)
        print(f"File: {filename}")
        print(f"  Path: {brain_path}")
        print(f"  Size: {size:,} bytes")
        print(f"  Last Modified: {mtime}\n")

if __name__ == "__main__":
    main()
