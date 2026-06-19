"""Quick audit: find issues with resolution language still marked OPEN."""
import json
from pathlib import Path

issues = json.loads(Path("outputs/issues/issues.json").read_text(encoding="utf-8"))

resolution_words = [
    "resolved", "fixed", "deployed", "successful", "confirmed",
    "merged", "passed", "completed", "released", "hotfix",
]

print("Issues with resolution language still OPEN:")
print("-" * 60)
for i in issues:
    if i["status"] == "OPEN":
        title_lower = i["title"].lower()
        for rw in resolution_words:
            if rw in title_lower:
                print(f"  [{i['severity']:8s}] {i['title']}")
                break

print()
print("Issues currently MONITORING:")
print("-" * 60)
for i in issues:
    if i["status"] == "MONITORING":
        print(f"  [{i['severity']:8s}] {i['title']}")

print()
print("Issues currently RESOLVED:")
print("-" * 60)
for i in issues:
    if i["status"] == "RESOLVED":
        evidence = i.get("resolution_summary", "N/A")
        print(f"  [{i['severity']:8s}] {i['title']}")
        print(f"            Evidence: {evidence}")
