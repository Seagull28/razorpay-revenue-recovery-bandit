"""
test_dashboard_smoke.py
Lightweight smoke test for dashboard.py structure, syntax compilation, and AST integrity.
Ensures dashboard.py remains valid without launching a blocking Streamlit server during test runs.
"""

import pytest
import ast
import py_compile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_dashboard_file_exists():
    dashboard_path = PROJECT_ROOT / "dashboard.py"
    assert dashboard_path.exists(), "dashboard.py must exist in project root!"
    assert dashboard_path.is_file(), "dashboard.py must be a file!"


def test_dashboard_syntax_compilation():
    dashboard_path = PROJECT_ROOT / "dashboard.py"
    # Verify Python compilation without executing UI commands
    compiled = py_compile.compile(str(dashboard_path), doraise=True)
    assert compiled is not None


def test_dashboard_ast_parsing_and_imports():
    dashboard_path = PROJECT_ROOT / "dashboard.py"
    content = dashboard_path.read_text(encoding="utf-8")
    
    # AST parse
    parsed_ast = ast.parse(content, filename="dashboard.py")
    assert isinstance(parsed_ast, ast.Module)

    # Inspect imports
    imported_names = set()
    for node in ast.walk(parsed_ast):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.add(node.module)

    # Verify critical dependencies are imported
    assert "streamlit" in imported_names
    assert any("bandit_retry_scheduler" in mod for mod in imported_names)
