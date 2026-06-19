import json
from pathlib import Path

clusters_file = Path("outputs/clusters/clusters.json")
report_file = Path("outputs/reports/2026-06-17_founder_report.json")

with open(clusters_file, "r") as f:
    clusters = json.load(f)

with open(report_file, "r") as f:
    report = json.load(f)

total_clusters = len(clusters)
total_issues_in_clusters = sum(len(c["supporting_issue_ids"]) for c in clusters)
avg_issues = total_issues_in_clusters / total_clusters if total_clusters > 0 else 0

single_issue_clusters = sum(1 for c in clusters if len(c["supporting_issue_ids"]) == 1)
multi_issue_clusters = total_clusters - single_issue_clusters

# Top recurring clusters
sorted_by_recurrence = sorted(clusters, key=lambda c: c["occurrence_count"], reverse=True)
top_recurring = [(c["title"], c["occurrence_count"]) for c in sorted_by_recurrence[:3]]

# Longest running clusters
sorted_by_days = sorted(clusters, key=lambda c: c["days_open"], reverse=True)
longest_running = [(c["title"], c["days_open"]) for c in sorted_by_days[:3]]

# Founder actionables count
actionables_count = len(report["founder_actionables"])

print("Validation Metrics:")
print(f"Total Clusters: {total_clusters}")
print(f"Average Issues per Cluster: {avg_issues:.2f}")
print(f"Single-issue Clusters Count: {single_issue_clusters}")
print(f"Multi-issue Clusters Count: {multi_issue_clusters}")
print(f"Top Recurring Clusters: {top_recurring}")
print(f"Longest Running Clusters (days): {longest_running}")
print(f"Founder Actionables count in report: {actionables_count}")
