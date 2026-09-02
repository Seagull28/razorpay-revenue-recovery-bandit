"""
create_project_zip.py
Exports a clean zip archive of the complete bandit_retry_scheduler codebase
including Phase 5 Tier 3 dashboard.py, evaluation reports, plots, and tests.
"""

import os
import zipfile
from pathlib import Path

def main():
    project_dir = Path(__file__).resolve().parent
    output_zip = project_dir.parent / "bandit_retry_scheduler_phase5_tier3_final.zip"

    ignore_dirs = {".git", "__pycache__", ".pytest_cache", ".streamlit"}
    ignore_extensions = {".pyc", ".pyo"}

    print("====================================================================================================")
    print("CREATING PROJECT ZIP ARCHIVE FOR INDEPENDENT VERIFICATION")
    print("====================================================================================================\n")

    file_count = 0
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for f in files:
                file_path = Path(root) / f
                if file_path.suffix in ignore_extensions:
                    continue
                if file_path == output_zip:
                    continue
                rel_path = file_path.relative_to(project_dir)
                zf.write(file_path, arcname=str(rel_path))
                file_count += 1

    stat = output_zip.stat()
    print(f"Archive Created : {output_zip.absolute()}")
    print(f"Total Files     : {file_count} files archived")
    print(f"Archive Size    : {stat.st_size:,} bytes")
    print("====================================================================================================")

if __name__ == "__main__":
    main()
