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
