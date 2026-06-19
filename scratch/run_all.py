import subprocess
import sys
from pathlib import Path

def main():
    files = [
        "11-06-2026.json",
        "12-06-2026.json",
        "13-06-2026.json",
        "14-06-2026.json",
        "15-06-2026.json",
        "16-06-2026.json",
        "17-06-2026.json"
    ]

    for f in files:
        print(f"\n==========================================")
        print(f" RUNNING PIPELINE FOR FILE: {f}")
        print(f"==========================================\n")
        
        # Resolve python executable from active venv if possible
        python_exe = sys.executable
        
        result = subprocess.run([python_exe, "run.py", f])
        if result.returncode != 0:
            print(f"\n[ERROR] Pipeline failed on file {f} with exit code {result.returncode}. Aborting.")
            sys.exit(result.returncode)

    print("\n==========================================")
    print(" BATCH PIPELINE RUN COMPLETED SUCCESSFULLY ")
    print("==========================================\n")

if __name__ == "__main__":
    main()
