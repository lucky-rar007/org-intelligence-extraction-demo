import json
from pathlib import Path

def categorize_issue(issue):
    title = issue["title"].lower()
    desc = issue["summary"].lower()
    text = title + " " + desc
    severity = issue["severity"]
    
    # Noise indicators: casual things, small reminders, personal things, minor tasks
    noise_keywords = [
        "movie", "dinner", "lunch", "eatfit", "cricket", "toit", "friday night", "reservation",
        "reminder", "reminders", "update ticket", "capacity adjustment", "sprint capacity",
        "board update", "postman collection", "capacity planning", "capacity review"
    ]
    
    # Founder relevant indicators: revenue risk, client escalation/risk, delivery risk, critical ops risk, strategic decisions
    founder_keywords = [
        "client xyz", "client abc", "payment gateway", "paytm", "double charge", "refund",
        "production database", "cpu spiking", "incident", "production deployment failed",
        "delivery delay", "delayed", "blocked", "escalation", "outage", "security", "vault",
        "merchant id", "revenue", "loss", "crash", "play store"
    ]
    
    # Let's check noise first
    if any(k in text for k in noise_keywords):
        return "NOISE"
        
    # If severity is HIGH or CRITICAL, it is almost always founder relevant
    if severity in ("HIGH", "CRITICAL"):
        return "FOUNDER_RELEVANT"
        
    # If it matches founder keywords and is at least MEDIUM
    if severity == "MEDIUM" and any(k in text for k in founder_keywords):
        return "FOUNDER_RELEVANT"
        
    # Default is team relevant (minor bugs, dev/staging tasks, technical debt, code checks)
    return "TEAM_RELEVANT"

def main():
    with open("outputs/issues/issues.json", "r") as f:
        issues = json.load(f)
        
    counts = {"FOUNDER_RELEVANT": 0, "TEAM_RELEVANT": 0, "NOISE": 0}
    categorized = {"FOUNDER_RELEVANT": [], "TEAM_RELEVANT": [], "NOISE": []}
    
    for issue in issues:
        cat = categorize_issue(issue)
        counts[cat] += 1
        categorized[cat].append(issue)
        
    print("--- CATEGORIZATION COUNTS ---")
    print(f"Total Issues: {len(issues)}")
    for cat, count in counts.items():
        print(f"{cat}: {count}")
        
    print("\n--- NOISE DETAILS ---")
    for iss in categorized["NOISE"][:15]:
        print(f"  - [{iss['severity']}] {iss['title']}")
        
    print("\n--- FOUNDER RELEVANT DETAILS ---")
    for iss in categorized["FOUNDER_RELEVANT"][:15]:
        print(f"  - [{iss['severity']}] {iss['title']} (occurrence: {iss['occurrence_count']})")

if __name__ == "__main__":
    main()
