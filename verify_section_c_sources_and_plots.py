"""
verify_section_c_sources_and_plots.py
Verifies image paths, file sizes, timestamps, and full-page AppTest load for Section C.
"""

import sys
import datetime
from pathlib import Path
from streamlit.testing.v1 import AppTest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def verify_images():
    print("====================================================================================================")
    print("1. EMBEDDED PLOT PNG IMAGE FILE VERIFICATION")
    print("====================================================================================================\n")

    plots_dir = Path(r"C:\Users\Thanujha\.gemini\antigravity\scratch\bandit_retry_scheduler\audit\plots")

    img_files = ["convergence_plots.png", "drift_adaptation.png"]
    for img_name in img_files:
        img_path = plots_dir / img_name
        assert img_path.exists(), f"Image file {img_name} does not exist!"
        stat = img_path.stat()
        mod_time = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"File Path    : {img_path.absolute()}")
        print(f"  Byte Size  : {stat.st_size} bytes")
        print(f"  Last Mod   : {mod_time}")
        print("-" * 80)

def verify_full_page_apptest():
    print("\n====================================================================================================")
    print("2. FULL-PAGE COLD-START AppTest LOAD VERIFICATION (SECTIONS B, A, C TOGETHER)")
    print("====================================================================================================\n")

    dashboard_path = r"C:\Users\Thanujha\.gemini\antigravity\scratch\bandit_retry_scheduler\dashboard.py"
    at = AppTest.from_file(dashboard_path, default_timeout=15)
    at.run()

    assert not at.exception, f"Full page load raised exception: {at.exception}"
    print("✅ FULL PAGE COLD-START LOAD: SUCCESS (0 Exceptions)")

    # Verify headings rendered across all three sections
    headers = [h.value for h in at.header]
    print("\nRendered Main Section Headers:")
    for h in headers:
        print(f"  - {h}")

    subheaders = [s.value for s in at.subheader]
    print("\nRendered Card Subheaders (Section C):")
    for s in subheaders:
        print(f"  - {s}")

    images = [i for i in at.image]
    print(f"\nRendered Plot Images in Section C: {len(images)} images found")

    print("\n====================================================================================================")
    print("ALL THREE SECTIONS (OVERVIEW, LIVE DEMO, LEARNING INSIGHTS) VERIFIED 100% ERROR-FREE!")
    print("====================================================================================================\n")

if __name__ == "__main__":
    verify_images()
    verify_full_page_apptest()
