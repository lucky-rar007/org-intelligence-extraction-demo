import os
import sys
import subprocess
import shutil
from pathlib import Path

# Ensure base directory is in path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from utils.date_utils import parse_filename_date
import config

def clear_directory_contents(dir_path: Path):
    """Clear all files in a directory except .gitkeep."""
    if not dir_path.exists():
        return
    for item in dir_path.iterdir():
        if item.is_file() and item.name != ".gitkeep":
            try:
                item.unlink()
                print(f"Deleted file: {item.relative_to(BASE_DIR)}")
            except Exception as e:
                print(f"Failed to delete {item}: {e}")
        elif item.is_dir():
            try:
                shutil.rmtree(item)
                print(f"Deleted directory: {item.relative_to(BASE_DIR)}")
            except Exception as e:
                print(f"Failed to delete directory {item}: {e}")

def main():
    print("=" * 60)
    print(" RUNNING ALL PIPELINE DAYS CHRONOLOGICALLY ")
    print("=" * 60)

    # 1. Ensure required directories exist
    config.create_required_directories()

    # 2. Clear previous outputs for a clean run
    print("\nCleaning outputs directory...")
    clear_directory_contents(config.EVENTS_OUTPUT_DIR)
    clear_directory_contents(config.OBSERVATIONS_OUTPUT_DIR)
    clear_directory_contents(config.ISSUES_OUTPUT_DIR)
    clear_directory_contents(config.CLUSTERS_OUTPUT_DIR)
    clear_directory_contents(config.REPORTS_OUTPUT_DIR)
    clear_directory_contents(config.LOGS_OUTPUT_DIR)

    # 3. Scan and sort RAW data files chronologically
    raw_dir = config.RAW_DATA_DIR
    raw_files = sorted(list(raw_dir.glob("*.json")), key=lambda f: parse_filename_date(f.name))

    print(f"\nFound {len(raw_files)} days to process:")
    for f in raw_files:
        date_obj = parse_filename_date(f.name)
        print(f"  - {f.name} (Date: {date_obj})")

    # Environment variables to enforce UTF-8 for subprocess stdout
    sub_env = os.environ.copy()
    sub_env["PYTHONIOENCODING"] = "utf-8"
    sub_env["PYTHONUTF8"] = "1"

    python_executable = sys.executable or "python"

    # 4. Run pipeline sequentially for each day
    reports_generated = []
    print("\nStarting execution...")
    for idx, file_path in enumerate(raw_files, 1):
        print("\n" + "#" * 60)
        print(f" Day {idx}/{len(raw_files)}: Processing {file_path.name}")
        print("#" * 60)

        cmd = [python_executable, "run.py", file_path.name]
        try:
            # We run run.py using subprocess to ensure clean state per execution
            result = subprocess.run(
                cmd,
                env=sub_env,
                capture_output=False, # Print directly to console so we can see real-time progress
                text=True,
                check=True
            )
            
            # Record the generated report path
            report_date = parse_filename_date(file_path.name).isoformat()
            report_file = config.REPORTS_OUTPUT_DIR / f"{report_date}_founder_report.json"
            if report_file.exists():
                reports_generated.append((file_path.name, report_file))
            else:
                reports_generated.append((file_path.name, "Not found"))

        except subprocess.CalledProcessError as e:
            print(f"\n[ERROR] Pipeline failed on {file_path.name} with exit code {e.returncode}")
            sys.exit(1)
        except Exception as e:
            print(f"\n[ERROR] Unexpected error when processing {file_path.name}: {e}")
            sys.exit(1)

    # 5. Final Summary of all runs
    print("\n" + "=" * 60)
    print(" ALL PIPELINE RUNS COMPLETED SUCCESSFULLY ")
    print("=" * 60)
    print("\nFinal Reports Generated:")
    for file_name, report_path in reports_generated:
        if isinstance(report_path, Path):
            rel_path = report_path.relative_to(BASE_DIR)
            print(f"  - Raw Input: {file_name} -> Report: {rel_path}")
        else:
            print(f"  - Raw Input: {file_name} -> Report: {report_path} (FAILED TO GENERATE)")
    print("=" * 60)

if __name__ == "__main__":
    main()
