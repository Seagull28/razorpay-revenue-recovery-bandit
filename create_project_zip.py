"""
create_project_zip.py
Exports a clean, portable ZIP archive of the complete bandit_retry_scheduler codebase.
Archives all project files under a single top-level `bandit_retry_scheduler/` directory.
Includes built-in ZIP member validation asserting 0 forbidden cache/git files.
"""

import os
import zipfile
from pathlib import Path

def main():
    project_dir = Path(__file__).resolve().parent
    output_zip = project_dir.parent / "bandit_retry_scheduler_phase5_tier3_final.zip"

    ignore_dirs = {".git", "__pycache__", ".pytest_cache", ".streamlit", ".venv", "venv", "env", "tmp_extract", "scratch"}
    ignore_extensions = {".pyc", ".pyo", ".zip", ".tmp", ".log"}

    print("====================================================================================================")
    print("CREATING PORTABLE SUBMISSION ZIP ARCHIVE FOR INDEPENDENT VERIFICATION")
    print("====================================================================================================\n")

    file_count = 0
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for f in files:
                file_path = Path(root) / f
                if file_path.suffix in ignore_extensions:
                    continue
                if file_path == output_zip or file_path.name.endswith(".zip"):
                    continue
                rel_path = file_path.relative_to(project_dir)
                arcname = str(Path("bandit_retry_scheduler") / rel_path)
                zf.write(file_path, arcname=arcname)
                file_count += 1

    # ZIP Member Validation
    forbidden_terms = [".git", "__pycache__", ".pytest_cache", ".pyc", ".venv", "venv"]
    invalid_members = []
    has_top_level = True

    with zipfile.ZipFile(output_zip, "r") as zf:
        members = zf.namelist()
        for member in members:
            # Verify single top-level directory
            if not member.startswith("bandit_retry_scheduler/"):
                has_top_level = False
                invalid_members.append(f"Non-top-level entry: {member}")
            
            # Verify forbidden items
            parts = member.split("/")
            for term in forbidden_terms:
                if term in parts or member.endswith(".pyc") or member.endswith(".zip"):
                    invalid_members.append(member)

    if invalid_members or not has_top_level:
        print(f"[FAIL] ZIP VALIDATION FAILED! Found {len(invalid_members)} validation errors:")
        for m in invalid_members[:10]:
            print(f"   - {m}")
        raise ValueError("ZIP Validation Failed!")
    else:
        print("[PASS] ZIP VALIDATION PASSED (Single top-level 'bandit_retry_scheduler/' folder, 0 forbidden git/cache/zip entries)")

    stat = output_zip.stat()
    print(f"Archive Created : {output_zip.absolute()}")
    print(f"Total Files     : {file_count} files archived")
    print(f"Archive Size    : {stat.st_size:,} bytes")
    print("====================================================================================================")

if __name__ == "__main__":
    main()
