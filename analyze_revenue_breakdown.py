"""
analyze_revenue_breakdown.py
Detailed per-failure-code financial breakdown comparing Fixed Baseline vs LinUCB.
Computes Gross Revenue Recovered, Total Retry Costs Incurred, Net Revenue, and Attempts.
"""

import json
from collections import defaultdict
from pathlib import Path


def analyze():
    base_file = Path("baseline_audit_log.json")
    bandit_file = Path("bandit_audit_log.json")

    with open(base_file, "r", encoding="utf-8") as f:
        base_data = json.load(f)

    with open(bandit_file, "r", encoding="utf-8") as f:
        bandit_data = json.load(f)

    def analyze_records(records):
        by_code = defaultdict(lambda: {
            "gross_revenue": 0.0,
            "retry_cost": 0.0,
            "attempts": 0,
            "tx_ids": set(),
            "recovered_ids": set(),
        })
        for r in records:
            code = r["context_vector"]["failure_code"]
            tx_id = r["transaction_id"]
            by_code[code]["tx_ids"].add(tx_id)
            by_code[code]["attempts"] += 1
            by_code[code]["retry_cost"] += 10.0
            if r["actual_outcome"] == 1:
                by_code[code]["recovered_ids"].add(tx_id)
                by_code[code]["gross_revenue"] += r["amount_recovered"]

        res = {}
        for code, d in by_code.items():
            res[code] = {
                "total_tx": len(d["tx_ids"]),
                "recovered_tx": len(d["recovered_ids"]),
                "rec_rate_pct": len(d["recovered_ids"]) / len(d["tx_ids"]) * 100.0 if d["tx_ids"] else 0.0,
                "gross_revenue": d["gross_revenue"],
                "retry_cost": d["retry_cost"],
                "net_revenue": d["gross_revenue"] - d["retry_cost"],
                "attempts": d["attempts"],
            }
        return res

    base_res = analyze_records(base_data["records"])
    bandit_res = analyze_records(bandit_data["records"])

    print("=" * 125)
    print("PER-FAILURE-CODE FINANCIAL COMPARISON: FIXED BASELINE vs. LinUCB BANDIT")
    print("=" * 125)
    header = f"{'Failure Code':<20} | {'Policy':<9} | {'Total Tx':<8} | {'Attempts':<8} | {'Rec Tx':<6} | {'Rec Rate':<8} | {'Gross Rev (INR)':<16} | {'Cost (INR)':<10} | {'Net Rev (INR)':<16}"
    print(header)
    print("-" * 125)

    for code in sorted(base_res.keys()):
        b = base_res[code]
        l = bandit_res[code]
        print(f"{code:<20} | {'Baseline':<9} | {b['total_tx']:>8} | {b['attempts']:>8} | {b['recovered_tx']:>6} | {b['rec_rate_pct']:>7.2f}% | INR {b['gross_revenue']:>12,.2f} | INR {b['retry_cost']:>6,.2f} | INR {b['net_revenue']:>12,.2f}")
        print(f"{code:<20} | {'LinUCB':<9} | {l['total_tx']:>8} | {l['attempts']:>8} | {l['recovered_tx']:>6} | {l['rec_rate_pct']:>7.2f}% | INR {l['gross_revenue']:>12,.2f} | INR {l['retry_cost']:>6,.2f} | INR {l['net_revenue']:>12,.2f}")
        
        diff_attempts = l['attempts'] - b['attempts']
        diff_rec = l['recovered_tx'] - b['recovered_tx']
        diff_rate = l['rec_rate_pct'] - b['rec_rate_pct']
        diff_gross = l['gross_revenue'] - b['gross_revenue']
        diff_cost = l['retry_cost'] - b['retry_cost']
        diff_net = l['net_revenue'] - b['net_revenue']
        
        print(f"{'  -> Delta (LinUCB-Base)':<20} | {'':<9} | {'':>8} | {diff_attempts:>+8} | {diff_rec:>+6} | {diff_rate:>+7.2f}% | INR {diff_gross:>+12,.2f} | INR {diff_cost:>+6,.2f} | INR {diff_net:>+12,.2f}")
        print("-" * 125)

    print("=" * 125)


if __name__ == "__main__":
    analyze()
