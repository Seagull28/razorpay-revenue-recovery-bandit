import sys
from pathlib import Path

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.simulator.config import BASE_RECOVERY_PROBABILITIES, FAILURE_CODES, BANKS, DELAY_ARMS

def verify_100_combinations():
    missing = []
    total = 0
    for code in FAILURE_CODES:
        for bank in BANKS:
            for delay in DELAY_ARMS:
                total += 1
                if code not in BASE_RECOVERY_PROBABILITIES:
                    missing.append((code, bank, delay, "code missing"))
                elif bank not in BASE_RECOVERY_PROBABILITIES[code]:
                    missing.append((code, bank, delay, "bank missing"))
                elif delay not in BASE_RECOVERY_PROBABILITIES[code][bank]:
                    missing.append((code, bank, delay, "delay missing"))
                    
    print(f"Verified total combinations: {total}")
    print(f"Missing combinations count: {len(missing)}")
    if missing:
        print("Missing items:", missing)
    else:
        print("SUCCESS: All 100 (failure_code x bank x delay) combinations are explicitly defined!")

if __name__ == "__main__":
    verify_100_combinations()
