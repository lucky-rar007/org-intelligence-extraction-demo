import json
from pathlib import Path
import re

def analyze_raw_data():
    raw_dir = Path("data/raw")
    raw_files = sorted(list(raw_dir.glob("*.json")))
    
    total_messages = 0
    total_threads = 0
    days = len(raw_files)
    
    for f in raw_files:
        with open(f, "r", encoding="utf-8") as file:
            messages = json.load(file)
            total_messages += len(messages)
            
            # Count threads (unique replyToId is null or thread starts)
            # Threads are grouped by either root message or replyToId
            roots = set()
            for msg in messages:
                tid = msg.get("replyToId")
                mid = msg.get("id")
                if tid is None:
                    roots.add(mid)
            total_threads += len(roots)
            
    avg_msg = total_messages / days
    avg_thread = total_threads / days
    
    print(f"--- RAW DATA STATS ---")
    print(f"Total Days: {days}")
    print(f"Total Messages: {total_messages} (Avg/day: {avg_msg:.2f})")
    print(f"Total Threads: {total_threads} (Avg/day: {avg_thread:.2f})")

def analyze_issues():
    issues_path = Path("outputs/issues/issues.json")
    if not issues_path.exists():
        print("issues.json not found!")
        return
        
    with open(issues_path, "r", encoding="utf-8") as f:
        issues = json.load(f)
        
    print(f"\n--- ISSUES STATS ---")
    print(f"Total Tracked Issues: {len(issues)}")
    
    # Let's count open/resolved issues
    open_issues = [i for i in issues if i["status"] in ("OPEN", "MONITORING")]
    resolved_issues = [i for i in issues if i["status"] == "RESOLVED"]
    stale_issues = [i for i in issues if i["status"] == "STALE"]
    
    print(f"Open Issues: {len(open_issues)}")
    print(f"Resolved Issues: {len(resolved_issues)}")
    print(f"Stale Issues: {len(stale_issues)}")
    
    # Calculate averages per day
    # June 11 to 17 = 7 days
    print(f"Avg issues generated/day: {len(issues) / 7:.2f}")

if __name__ == "__main__":
    analyze_raw_data()
    analyze_issues()
