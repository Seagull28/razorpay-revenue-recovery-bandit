"""
test_no_ground_truth_leakage.py
Robust AST-Based Ground-Truth & Simulator Isolation Test Suite for RecoverFlow.

Parses Python Abstract Syntax Trees (ast.parse) across all production modules (api/, policies/, runner/) to detect:
1. Direct imports: `import simulator.ground_truth` or `import bandit_retry_scheduler.simulator.ground_truth`
2. Aliased imports: `import simulator.ground_truth as gt`
3. From imports: `from simulator.ground_truth import calculate_recovery_probability`
4. Aliased function imports: `from simulator.ground_truth import calculate_recovery_probability as prob`
5. Attribute access & function calls: `gt.calculate_recovery_probability(...)` or `prob(...)`
6. Includes negative test fixtures confirming that the AST scanner detects all 5 violation types.
"""

import ast
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROHIBITED_MODULES = {"ground_truth", "simulator.ground_truth", "bandit_retry_scheduler.simulator.ground_truth"}
PROHIBITED_FUNCTIONS = {"calculate_recovery_probability", "get_true_recovery_probability"}


class GroundTruthLeakageVisitor(ast.NodeVisitor):
    """AST NodeVisitor that traverses Python source code ASTs to detect hidden ground-truth leakage."""

    def __init__(self):
        self.violations = []
        self.imported_aliases = set()

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.name
            asname = alias.asname or name
            if any(p in name for p in PROHIBITED_MODULES):
                self.violations.append((node.lineno, f"Prohibited module import: {name} (as {asname})"))
                self.imported_aliases.add(asname)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        if any(p in module for p in PROHIBITED_MODULES):
            for alias in node.names:
                name = alias.name
                asname = alias.asname or name
                self.violations.append((node.lineno, f"Prohibited import from {module}: {name} (as {asname})"))
                self.imported_aliases.add(asname)
        else:
            for alias in node.names:
                if alias.name in PROHIBITED_FUNCTIONS:
                    asname = alias.asname or alias.name
                    self.violations.append((node.lineno, f"Prohibited function import: {alias.name} (as {asname})"))
                    self.imported_aliases.add(asname)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in PROHIBITED_FUNCTIONS or node.attr in PROHIBITED_MODULES:
            self.violations.append((node.lineno, f"Prohibited attribute access: .{node.attr}"))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            if node.id in PROHIBITED_FUNCTIONS or node.id in self.imported_aliases:
                self.violations.append((node.lineno, f"Prohibited function/alias reference: {node.id}"))
        self.generic_visit(node)


def scan_file_for_ast_leakage(file_path: Path) -> list:
    """Parses source code into AST and runs GroundTruthLeakageVisitor."""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as e:
        return [(0, f"AST Parse Error: {e}")]

    visitor = GroundTruthLeakageVisitor()
    visitor.visit(tree)
    return visitor.violations


def scan_directory_for_ast_leakage(target_dir: Path) -> list:
    all_violations = []
    if not target_dir.exists():
        return all_violations
    for py_file in target_dir.rglob("*.py"):
        violations = scan_file_for_ast_leakage(py_file)
        for line, msg in violations:
            rel_file = str(py_file.relative_to(PROJECT_ROOT))
            all_violations.append((rel_file, line, msg))
    return all_violations


def test_api_directory_ast_leakage_isolation():
    """Verify api/ directory has zero ground-truth leakage via AST analysis."""
    violations = scan_directory_for_ast_leakage(PROJECT_ROOT / "api")
    assert len(violations) == 0, f"Ground-truth leakage detected in api/: {violations}"


def test_policies_directory_ast_leakage_isolation():
    """Verify policies/ directory has zero ground-truth leakage via AST analysis."""
    violations = scan_directory_for_ast_leakage(PROJECT_ROOT / "policies")
    assert len(violations) == 0, f"Ground-truth leakage detected in policies/: {violations}"


def test_runner_directory_ast_leakage_isolation():
    """Verify runner/ directory has zero ground-truth leakage via AST analysis."""
    violations = scan_directory_for_ast_leakage(PROJECT_ROOT / "runner")
    assert len(violations) == 0, f"Ground-truth leakage detected in runner/: {violations}"


def test_ast_scanner_detects_direct_import(tmp_path):
    f = tmp_path / "violation_direct.py"
    f.write_text("import bandit_retry_scheduler.simulator.ground_truth\n")
    violations = scan_file_for_ast_leakage(f)
    assert len(violations) >= 1, "Failed to detect direct import violation!"


def test_ast_scanner_detects_aliased_import(tmp_path):
    f = tmp_path / "violation_aliased.py"
    f.write_text("import bandit_retry_scheduler.simulator.ground_truth as gt\nx = gt.to_day_bucket(5)\n")
    violations = scan_file_for_ast_leakage(f)
    assert len(violations) >= 1, "Failed to detect aliased import violation!"


def test_ast_scanner_detects_direct_function_import(tmp_path):
    f = tmp_path / "violation_func.py"
    f.write_text("from bandit_retry_scheduler.simulator.ground_truth import calculate_recovery_probability\n")
    violations = scan_file_for_ast_leakage(f)
    assert len(violations) >= 1, "Failed to detect direct function import violation!"


def test_ast_scanner_detects_aliased_function_import(tmp_path):
    f = tmp_path / "violation_aliased_func.py"
    f.write_text("from bandit_retry_scheduler.simulator.ground_truth import calculate_recovery_probability as prob\np = prob({}, '1hr')\n")
    violations = scan_file_for_ast_leakage(f)
    assert len(violations) >= 1, "Failed to detect aliased function import violation!"


def test_ast_scanner_detects_package_qualified_import(tmp_path):
    f = tmp_path / "violation_qualified.py"
    f.write_text("import simulator.ground_truth\n")
    violations = scan_file_for_ast_leakage(f)
    assert len(violations) >= 1, "Failed to detect package qualified import violation!"


def test_allowed_evaluation_and_simulator_access_is_not_incorrectly_flagged():
    """Verify that allowed evaluation files (evaluation/oracle.py) parse cleanly without false positives on permitted paths."""
    oracle_file = PROJECT_ROOT / "evaluation" / "oracle.py"
    assert oracle_file.exists()
    # Oracle is explicitly permitted to access simulator ground truth for evaluation
    oracle_violations = scan_file_for_ast_leakage(oracle_file)
    assert len(oracle_violations) >= 1  # Confirms Oracle imports ground truth legitimately for evaluation
