"""
verify_no_lpha.py
Grep all evaluation_report.md files for broken ASCII bell \\x07lpha or unescaped $lpha$
and print clean section 10 header.
"""

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

paths = [
    Path(r"C:\Users\Thanujha\.gemini\antigravity\scratch\bandit_retry_scheduler\evaluation_report.md"),
    Path(r"C:\Users\Thanujha\.gemini\antigravity\scratch\bandit_retry_scheduler\audit\evaluation_report.md"),
    Path(r"C:\Users\Thanujha\.gemini\antigravity\brain\30eeb98e-59ae-47b5-85ad-a23d7f580f5a\evaluation_report.md"),
]

for p in paths:
    with open(p, "r", encoding="utf-8") as f:
        content = f.read()
    
    lines = content.split("\n")
    print(f"Checking {p.name} ({p.parent}):")
    
    broken_lines = []
    for idx, line in enumerate(lines, 1):
        if "\x07lpha" in line or "$ lpha$" in line or "$lpha$" in line:
            broken_lines.append((idx, line))
    
    if broken_lines:
        print(f"  FAILED: Found {len(broken_lines)} broken 'lpha' instances:")
        for lno, ltext in broken_lines:
            print(f"    Line {lno}: {ltext}")
    else:
        print("  PASSED: 0 broken '\\x07lpha' / '$ lpha$' instances found!")

    # Print Section 10 Header
    sec10_line = [line for line in lines if "10. LinUCB" in line]
    print(f"  Section 10 Header: {sec10_line}\n")
