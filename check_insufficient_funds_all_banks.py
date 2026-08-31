import sys
from pathlib import Path

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.simulator.config import BASE_RECOVERY_PROBABILITIES, FailureCode, Bank, DELAY_ARMS
from bandit_retry_scheduler.simulator.ground_truth import calculate_recovery_probability

def main():
    print("=" * 80)
    print("GROUND TRUTH ANALYSIS: INSUFFICIENT FUNDS ACROSS ALL 4 BANKS")
    print("=" * 80)
    
    # Base recovery probabilities from config.py
    base_probs = BASE_RECOVERY_PROBABILITIES[FailureCode.INSUFFICIENT_FUNDS.value]
    
    print("\n1. BASE RECOVERY PROBABILITIES P(recover | insufficient_funds, bank, delay):")
    print(f"| Bank | 1hr | 6hr | 1d | 3d | 7d | Optimal Delay Arm |")
    print(f"| :--- | :---: | :---: | :---: | :---: | :---: | :--- |")
    for bank_name in [Bank.BANK_A.value, Bank.BANK_B.value, Bank.BANK_C.value, Bank.BANK_D.value]:
        curves = base_probs[bank_name]
        best_arm = max(curves, key=curves.get)
        print(f"| {bank_name} | {curves['1hr']*100:.0f}% | {curves['6hr']*100:.0f}% | {curves['1d']*100:.0f}% | {curves['3d']*100:.0f}% | {curves['7d']*100:.0f}% | **{best_arm}** ({curves[best_arm]*100:.0f}%) |")

    # Full ground truth calculation for a typical context (amount = ₹5,000 median)
    sample_ctx_base = {
        "failure_code": FailureCode.INSUFFICIENT_FUNDS.value,
        "network": "Visa",
        "retry_attempt_number": 1,
        "day_of_month_bucket": "mid",
        "customer_prior_success_count": "1-3",
        "customer_prior_failures_this_cycle": "0",
        "amount": 5000.0,
    }
    
    print("\n2. FULL CONTEXT EXPECTED NET REVENUE (Amount = ₹5,000, Visa, Mid-month):")
    print(f"| Bank | 1hr EV | 6hr EV | 1d EV | 3d EV | 7d EV | Optimal Delay Arm |")
    print(f"| :--- | :---: | :---: | :---: | :---: | :---: | :--- |")
    for bank_name in [Bank.BANK_A.value, Bank.BANK_B.value, Bank.BANK_C.value, Bank.BANK_D.value]:
        ctx = dict(sample_ctx_base)
        ctx["bank"] = bank_name
        evs = {}
        for delay in DELAY_ARMS:
            p = calculate_recovery_probability(ctx, delay)
            evs[delay] = p * 5000.0 - 10.0
        best_arm = max(evs, key=evs.get)
        print(f"| {bank_name} | ₹{evs['1hr']:,.0f} | ₹{evs['6hr']:,.0f} | ₹{evs['1d']:,.0f} | ₹{evs['3d']:,.0f} | ₹{evs['7d']:,.0f} | **{best_arm}** (₹{evs[best_arm]:,.0f}) |")

if __name__ == "__main__":
    main()
