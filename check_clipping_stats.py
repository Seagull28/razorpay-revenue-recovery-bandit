import sys
from pathlib import Path
import numpy as np

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.simulator.config import AMOUNT_DISTRIBUTION_PARAMS, AMOUNT_DISTRIBUTION_MAPPING, FAILURE_CODES, BANKS, DELAY_ARMS, BASE_RECOVERY_PROBABILITIES
from bandit_retry_scheduler.simulator.stream_generator import TransactionStreamGenerator

def main():
    gen = TransactionStreamGenerator(seed=42)
    txs = gen.generate_stream(num_days=30, transactions_per_day=100)
    
    total = len(txs)
    min_clipped = 0
    max_clipped = 0
    
    for tx in txs:
        code = tx["failure_code"]
        amt = tx["amount"]
        dist_type = AMOUNT_DISTRIBUTION_MAPPING[code]
        params = AMOUNT_DISTRIBUTION_PARAMS[dist_type]
        
        if amt <= params["min_amount"]:
            min_clipped += 1
        elif amt >= params["max_amount"]:
            max_clipped += 1
            
    print(f"Total transactions: {total}")
    print(f"Clipped to min_amount: {min_clipped} ({min_clipped/total*100:.2f}%)")
    print(f"Clipped to max_amount: {max_clipped} ({max_clipped/total*100:.2f}%)")

if __name__ == "__main__":
    main()
