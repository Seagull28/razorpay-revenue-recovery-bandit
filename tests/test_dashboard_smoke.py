"""
test_dashboard_smoke.py
Real smoke test for dashboard.py: actually executes the app end-to-end using
Streamlit's AppTest framework and asserts no unhandled exception occurred.
Structural checks (file exists, compiles, imports) are kept as fast pre-checks,
but the critical check is at.exception being empty after a real run.
"""

import pytest
import ast
import py_compile
from pathlib import Path
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_dashboard_file_exists():
    dashboard_path = PROJECT_ROOT / "dashboard.py"
    assert dashboard_path.exists(), "dashboard.py must exist in project root!"
    assert dashboard_path.is_file(), "dashboard.py must be a file!"


def test_dashboard_syntax_compilation():
    dashboard_path = PROJECT_ROOT / "dashboard.py"
    compiled = py_compile.compile(str(dashboard_path), doraise=True)
    assert compiled is not None


def test_dashboard_ast_parsing_and_imports():
    dashboard_path = PROJECT_ROOT / "dashboard.py"
    content = dashboard_path.read_text(encoding="utf-8")
    parsed_ast = ast.parse(content, filename="dashboard.py")
    assert isinstance(parsed_ast, ast.Module)

    imported_names = set()
    for node in ast.walk(parsed_ast):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.add(node.module)

    assert "streamlit" in imported_names
    assert any("bandit_retry_scheduler" in mod for mod in imported_names)


def test_dashboard_actually_runs_without_exception():
    """
    CRITICAL: actually executes dashboard.py top-to-bottom via Streamlit's
    AppTest framework. This is the only test in this file that would have
    caught either the simulator.step() AttributeError or the phase1_summary
    KeyError crash — the tests above only check syntax, not runtime behavior.
    """
    at = AppTest.from_file(str(PROJECT_ROOT / "dashboard.py"), default_timeout=60)
    at.run()
    assert not at.exception, (
        f"dashboard.py raised an unhandled exception on a real run: {at.exception}"
    )


def test_dashboard_section1_metrics_render():
    """Confirms Section 1's metric cards and 5-policy table actually populate,
    not just that the script didn't crash."""
    at = AppTest.from_file(str(PROJECT_ROOT / "dashboard.py"), default_timeout=60)
    at.run()
    assert not at.exception
    # At least the 4 top-line st.metric cards from Section 1 must be present
    assert len(at.metric) >= 4, f"Expected at least 4 metric cards, found {len(at.metric)}"


def test_dashboard_all_preset_transactions_render():
    """Cycles through every preset transaction option and confirms no exception,
    including the Card Expired hard-stop case which should recommend HALT rather
    than a retry delay."""
    at = AppTest.from_file(str(PROJECT_ROOT / "dashboard.py"), default_timeout=60)
    at.run()
    assert not at.exception

    # Find the preset selectbox by checking its current options include the known presets
    target = None
    for sb in at.selectbox:
        if any("Insufficient Funds" in str(opt) for opt in sb.options):
            target = sb
            break
    assert target is not None, "Could not locate the preset transaction selectbox"

    for option in target.options:
        target.select(option).run()
        assert not at.exception, f"Exception when selecting preset '{option}': {at.exception}"


def test_dashboard_all_strategy_modes_render():
    """Cycles through every Strategy Mode option and confirms no exception."""
    at = AppTest.from_file(str(PROJECT_ROOT / "dashboard.py"), default_timeout=60)
    at.run()
    assert not at.exception

    target = None
    for sb in at.selectbox:
        if set(sb.options) >= {"BALANCED", "MAXIMIZE_RECOVERY", "CONSERVATIVE"}:
            target = sb
            break
    assert target is not None, "Could not locate the Strategy Mode selectbox"

    for option in target.options:
        target.select(option).run()
        assert not at.exception, f"Exception when selecting strategy mode '{option}': {at.exception}"


def test_dashboard_custom_transaction_entry_renders():
    """Selects 'Custom Transaction Entry' and confirms the custom input form
    renders without exception."""
    at = AppTest.from_file(str(PROJECT_ROOT / "dashboard.py"), default_timeout=60)
    at.run()
    assert not at.exception

    preset_sb = None
    for sb in at.selectbox:
        if any("Custom Transaction Entry" in str(opt) for opt in sb.options):
            preset_sb = sb
            break
    assert preset_sb is not None, "Could not locate the preset selectbox"

    preset_sb.select("Custom Transaction Entry").run()
    assert not at.exception, f"Exception on Custom Transaction Entry: {at.exception}"
    # After selecting custom entry, additional selectboxes/number_inputs for the
    # custom form should now be present
    assert len(at.selectbox) > 2, "Custom entry form widgets did not appear"


def test_dashboard_execute_retry_action_button():
    """Clicks the Execute Retry Action button on the default preset and confirms
    the action completes without exception and a success message renders."""
    at = AppTest.from_file(str(PROJECT_ROOT / "dashboard.py"), default_timeout=60)
    at.run()
    assert not at.exception

    exec_button = None
    for btn in at.button:
        if "Execute Retry Action" in str(btn.label):
            exec_button = btn
            break
    assert exec_button is not None, "Could not locate the Execute Retry Action button"

    exec_button.click().run()
    assert not at.exception, f"Exception when clicking Execute Retry Action: {at.exception}"
    # A success message should appear after execution
    assert len(at.success) > 0, "No success message rendered after executing retry action"


def test_dashboard_card_expired_hard_stop_shows_halt():
    """Specifically verifies the Card Expired preset (a hard-stop case) renders
    a HALT recommendation rather than crashing or showing a bogus delay."""
    at = AppTest.from_file(str(PROJECT_ROOT / "dashboard.py"), default_timeout=60)
    at.run()
    assert not at.exception

    preset_sb = None
    for sb in at.selectbox:
        if any("Card Expired" in str(opt) for opt in sb.options):
            preset_sb = sb
            break
    assert preset_sb is not None

    card_expired_option = next(opt for opt in preset_sb.options if "Card Expired" in opt)
    preset_sb.select(card_expired_option).run()
    assert not at.exception, f"Exception on Card Expired preset: {at.exception}"

    # At least one metric should show HALT for the Recommended Delay
    metric_values = [m.value for m in at.metric]
    assert any("HALT" in str(v) for v in metric_values), (
        f"Expected a HALT recommendation for Card Expired hard-stop, got metrics: {metric_values}"
    )
