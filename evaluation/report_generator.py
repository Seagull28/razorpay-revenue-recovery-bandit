"""
report_generator.py
Generates human-readable Markdown evaluation report.
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
    Delegates to canonical Phase 1 markdown report generator.
    """
    from bandit_retry_scheduler.run_phase1_evaluation import generate_phase1_markdown_report
    summary_data = eval_results.get("summary_by_policy", eval_results.get("summary", {}))
    paired_data = eval_results.get("paired_comparisons", eval_results.get("paired", {}))
    fingerprint = eval_results.get("evaluation_fingerprint", eval_results.get("fingerprint", {}))
    
    report_text = generate_phase1_markdown_report(summary_data, paired_data, fingerprint)
    if output_report_path:
        out_file = Path(output_report_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(report_text, encoding="utf-8")
    return report_text
