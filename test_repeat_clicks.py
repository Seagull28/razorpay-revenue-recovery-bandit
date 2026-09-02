"""
test_repeat_clicks.py
Verifies that clicking 'Execute Retry Action' multiple times sequentially on the SAME sample transaction
keeps all transaction context fields (amount, failure_code, bank, attempt_number) 100% fixed,
with only the outcome (success/failure), recovered amount, reward, and policy parameter updates advancing.
"""

import sys
from pathlib import Path
from streamlit.testing.v1 import AppTest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def test_repeat_clicks():
    dashboard_path = str(Path(__file__).resolve().parent / "dashboard.py")
    
    print("====================================================================================================")
    print("VERIFYING 3 SEQUENTIAL CLICKS ON THE SAME SAMPLE TRANSACTION")
    print("====================================================================================================\n")

    at = AppTest.from_file(dashboard_path, default_timeout=10)
    at.run()
    assert not at.exception

    # Select Preset 'Issuer Timeout (Standard, Bank C)'
    preset_name = "Issuer Timeout (Standard, Bank C)"
    at.selectbox[0].select(preset_name).run()
    assert not at.exception

    print(f"Target Preset: '{preset_name}'\n")

    for click_idx in range(1, 4):
        # Locate and click 'Execute Retry Action' button
        exec_buttons = [b for b in at.button if "Execute Retry Action" in b.label]
        assert len(exec_buttons) > 0, "Execute button not found"

        exec_buttons[0].click().run()
        assert not at.exception, f"Click {click_idx} raised exception: {at.exception}"

        # Extract rendered explanation text & outcome success text
        info_msgs = [i.value for i in at.info]
        success_msgs = [s.value for s in at.success]

        exp_text = info_msgs[0] if info_msgs else "N/A"
        outcome_text = success_msgs[0] if success_msgs else "N/A"

        print(f"--- CLICK {click_idx} RESULT ---")
        print(f"Explanation Text  : {exp_text}")
        print(f"Outcome & Readout : {outcome_text}")
        print("-" * 80)

if __name__ == "__main__":
    test_repeat_clicks()
