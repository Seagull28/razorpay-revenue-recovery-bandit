"""
locate_all_reports.py
Locates every evaluation_report.md file in the workspace, prints its exact path, timestamp, size,
and section headers.
"""

from pathlib import Path
import datetime

def main():
    root = Path(r"C:\Users\Thanujha\.gemini\antigravity")
    matches = list(root.glob("**/evaluation_report.md"))

    print(f"Found {len(matches)} evaluation_report.md file(s):\n")

    for p in matches:
        stat = p.stat()
        mod_time = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"File: {p.absolute()}")
        print(f"  Size     : {stat.st_size} bytes")
        print(f"  Modified : {mod_time}")

        with open(p, "r", encoding="utf-8") as f:
            lines = f.readlines()
        headers = [l.strip() for l in lines if l.startswith("## ")]
        print(f"  Headers ({len(headers)} found):")
        for h in headers:
            print(f"    - {h}")
        print("-" * 80)

if __name__ == "__main__":
    main()
