"""
test_streamlit_apptest.py
Automated programmatic test of dashboard.py using streamlit.testing.v1.AppTest.
Loads dashboard.py, iterates through all 5 preset sample transactions, verifies
clean error-free rendering, clicks the Execute Retry Action button, and reports
the actual session state and rendered outputs.
"""

import sys
from pathlib import Path
from streamlit.testing.v1 import AppTest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def test_dashboard_apptest():
    dashboard_path = str(Path(__file__).resolve().parent / "dashboard.py")
    
    print("====================================================================================================")
    print("STREAMLIT AppTest PROGRAMMATIC INTERACTION TEST FOR DASHBOARD.PY")
    print("====================================================================================================\n")

    presets = [
        "Insufficient Funds (High-Ticket, Bank B)",
        "Issuer Timeout (Standard, Bank C)",
        "Do Not Honor (High-Ticket, Bank A)",
        "Card Expired (Unrecoverable Hard Stop, Bank D)",
        "Generic Decline (Standard, Bank A)",
    ]

    at = AppTest.from_file(dashboard_path, default_timeout=10)
    at.run()

    assert not at.exception, f"Initial page load raised an exception: {at.exception}"
    print("✅ INITIAL DASHBOARD PAGE LOAD: SUCCESS (0 Exceptions)")

    for idx, preset_name in enumerate(presets, 1):
        print(f"\n----------------------------------------------------------------------------------------------------")
        print(f"INTERACTION {idx}/5: Testing Preset '{preset_name}'")
        print(f"----------------------------------------------------------------------------------------------------")

        # Select preset in selectbox
        at.selectbox[0].select(preset_name).run()
        assert not at.exception, f"Selecting preset '{preset_name}' raised an exception: {at.exception}"

        # Inspect rendered markdown banners
        markdown_texts = [m.value for m in at.markdown]
        banner = [m for m in markdown_texts if "ELIGIBLE" in m or "INELIGIBLE" in m]
        print(f"  - Eligibility Banner : {banner[0] if banner else 'No banner found'}")

        # Locate and click 'Execute Retry Action' button
        exec_buttons = [b for b in at.button if "Execute Retry Action" in b.label]
        assert len(exec_buttons) > 0, "Execute Retry Action button not found"

        exec_buttons[0].click().run()
        assert not at.exception, f"Clicking Execute Retry Action for '{preset_name}' raised an exception: {at.exception}"

        # Inspect execution result outputs
        success_msgs = [s.value for s in at.success]
        info_msgs = [i.value for i in at.info]
        
        print(f"  - Execution Outcome  : {success_msgs[0] if success_msgs else 'No success message (e.g. stopped decision)'}")
        print(f"  - Explanation Text   : {info_msgs[0][:120]}..." if info_msgs else "  - Explanation Text: N/A")
        print(f"  - AppTest Exceptions : NONE (Clean execution)")

    print("\n====================================================================================================")
    print("ALL 5 SAMPLE TRANSACTIONS & BUTTON CLICKS VERIFIED 100% ERROR-FREE VIA AppTest!")
    print("====================================================================================================")

if __name__ == "__main__":
    test_dashboard_apptest()
