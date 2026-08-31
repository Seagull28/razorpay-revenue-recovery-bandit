import sys
from pathlib import Path

sys.path.append(r"C:\Users\Thanujha\.gemini\antigravity\scratch")

from bandit_retry_scheduler.evaluation.harness import EvaluationHarness

def main():
    harness = EvaluationHarness(seeds=[42], num_days=30, transactions_per_day=100)
    seed_res = harness.run_seed_benchmark(42)
    records = seed_res["linucb_records"]
    
    # Filter for issuer_timeout specifically
    timeout_records = [r for r in records if r["context_vector"]["failure_code"] == "issuer_timeout"]
    
    # Group by transaction_id to get unique transaction order
    tx_order = []
    seen = set()
    for r in timeout_records:
        tx_id = r["transaction_id"]
        if tx_id not in seen:
            seen.add(tx_id)
            tx_order.append(tx_id)
            
    print(f"Total issuer_timeout transactions: {len(tx_order)}")
    
    first_100_ids = set(tx_order[:100])
    last_100_ids = set(tx_order[-100:])
    
    def summarize(tx_ids):
        recs = [r for r in timeout_records if r["transaction_id"] in tx_ids]
        recovered = {r["transaction_id"] for r in recs if r["actual_outcome"] == 1}
        attempts = len(recs)
        gross = sum(r["amount_recovered"] for r in recs if r["actual_outcome"] == 1)
        cost = attempts * 10.0
        net = gross - cost
        n = len(tx_ids)
        return {
            "total_tx": n,
            "recovered_tx": len(recovered),
            "rec_rate_pct": (len(recovered) / n * 100.0) if n > 0 else 0.0,
            "gross": gross,
            "cost": cost,
            "net": net,
            "attempts": attempts,
            "net_per_tx": net / n if n > 0 else 0.0,
        }
        
    f100 = summarize(first_100_ids)
    l100 = summarize(last_100_ids)
    
    print("\n--- FIRST 100 issuer_timeout ---")
    print(f"Recovery Rate : {f100['rec_rate_pct']:.2f}% ({f100['recovered_tx']}/100)")
    print(f"Gross Revenue : INR {f100['gross']:,.2f}")
    print(f"Retry Cost    : INR {f100['cost']:,.2f} ({f100['attempts']} attempts)")
    print(f"Net Revenue   : INR {f100['net']:,.2f} (INR {f100['net_per_tx']:.2f}/tx)")
    
    print("\n--- LAST 100 issuer_timeout ---")
    print(f"Recovery Rate : {l100['rec_rate_pct']:.2f}% ({l100['recovered_tx']}/100)")
    print(f"Gross Revenue : INR {l100['gross']:,.2f}")
    print(f"Retry Cost    : INR {l100['cost']:,.2f} ({l100['attempts']} attempts)")
    print(f"Net Revenue   : INR {l100['net']:,.2f} (INR {l100['net_per_tx']:.2f}/tx)")

if __name__ == "__main__":
    main()
