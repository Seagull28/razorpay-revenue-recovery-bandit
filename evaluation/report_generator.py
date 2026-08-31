"""
report_generator.py
Generates the comprehensive 11-section Markdown evaluation report incorporating
multi-seed tables, detailed segment breakdowns, regret curves, arm convergence,
cold-start analysis, drift adaptation results, 10-seed bootstrap CIs, adaptive threshold experiments,
alpha sensitivity analysis, and sim-to-real considerations.
"""

from pathlib import Path
from typing import Any, Dict


def generate_evaluation_report(
    eval_results: Dict[str, Any],
    output_report_path: str,
    plots_relative_dir: str = "plots",
) -> str:
    """
    Formally formats evaluation results into a Markdown report.
    Delegates to build_full_project_report.py logic if output_report_path is specified.
    """
    from bandit_retry_scheduler.build_full_project_report import main as build_main
    build_main()
    
    with open(output_report_path, "r", encoding="utf-8") as f:
        return f.read()
