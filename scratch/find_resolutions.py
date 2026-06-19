import json
from pathlib import Path

def main():
    # Load all issues
    with open("outputs/issues/issues.json", "r") as f:
        issues = json.load(f)
        
    # Let's inspect raw messages for resolution indicators
    raw_dir = Path("data/raw")
    raw_files = sorted(list(raw_dir.glob("*.json")))
    
    all_msgs = []
    for rf in raw_files:
        with open(rf, "r", encoding="utf-8") as f:
            all_msgs.extend(json.load(f))
            
    print(f"Loaded {len(issues)} issues and {len(all_msgs)} raw messages.")
    
    resolution_keywords = ["resolved", "fixed", "completed", "deployed", "verified", "closed", "patched", "merged", "shipped", "working now", "gone", "stable"]
    
    # We want to trace specific issues
    # Let's look at issues with words like "CORS", "Paytm", "Webhook", "Staging", "Build", "Database"
    for issue in issues:
        title = issue["title"].lower()
        # Find messages that mention similar keywords AND have resolution keywords
        words = [w for w in title.split() if len(w) > 3 and w not in ["issue", "issues", "problem", "problems", "error", "errors", "failed", "failure", "delay", "delays"]]
        
        matches = []
        for msg in all_msgs:
            content = msg["body"]["content"].lower()
            # If message timestamp is after the issue first_seen
            if msg["createdDateTime"] >= issue["first_seen"]:
                # Check keyword overlap
                if any(w in content for w in words):
                    # Check resolution language
                    if any(rk in content for rk in resolution_keywords):
                        matches.append((msg["createdDateTime"], msg["from"]["user"]["displayName"], msg["body"]["content"]))
                        
        if matches:
            print(f"\nIssue: [{issue['id']}] '{issue['title']}' (First seen: {issue['first_seen']})")
            for dt, sender, text in matches[:3]:
                print(f"  -> {dt} by {sender}: {text[:140]}...")

if __name__ == "__main__":
    main()
