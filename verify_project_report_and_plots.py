"""
verify_project_report_and_plots.py
Independently inspects and verifies the saved evaluation_report.md and plot artifacts
in the project workspace folder (audit/).
"""

import os
from pathlib import Path
import datetime

def main():
    report_path = Path(r"C:\Users\Thanujha\.gemini\antigravity\scratch\bandit_retry_scheduler\audit\evaluation_report.md")
    plots_dir = Path(r"C:\Users\Thanujha\.gemini\antigravity\scratch\bandit_retry_scheduler\audit\plots")

    print("====================================================================================================")
    print("INDEPENDENT FILE VERIFICATION FOR PROJECT WORKSPACE")
    print("====================================================================================================\n")

    print(f"1. REPORT FILE PATH: {report_path.absolute()}")
    assert report_path.exists(), "Report file does not exist!"

    stat = report_path.stat()
    mod_time = datetime.datetime.fromtimestamp(stat.st_mtime)
    print(f"   - File Byte Size : {stat.st_size} bytes")
    print(f"   - Last Modified  : {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Read lines and extract all "## " section headers
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    headers = [line.strip() for line in lines if line.startswith("## ")]

    print("\n2. SECTION HEADERS FOUND IN SAVED REPORT:")
    for h in headers:
        print(f"   - {h}")

    print("\n3. PLOTS DIRECTORY VERIFICATION:")
    print(f"   - Plots Directory: {plots_dir.absolute()}")
    assert plots_dir.exists(), "Plots directory does not exist!"

    plot_files = list(plots_dir.glob("*.png"))
    for p in plot_files:
        p_stat = p.stat()
        p_time = datetime.datetime.fromtimestamp(p_stat.st_mtime)
        print(f"   - Image File : {p.name}")
        print(f"     Size       : {p_stat.st_size} bytes")
        print(f"     Modified   : {p_time.strftime('%Y-%m-%d %H:%M:%S')}")

    print("\n====================================================================================================")

if __name__ == "__main__":
    main()
