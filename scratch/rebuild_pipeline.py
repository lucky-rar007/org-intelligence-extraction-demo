"""Rebuild the issue tracker, aggregation, and reports from existing extracted events.

This script does NOT re-run LLM extraction. It re-processes the stored events
through the updated pipeline stages:
1. Clear existing issue state
2. Process events for each date in chronological order
3. Run aggregation and report generation for each date
4. Print validation summary

Usage:
    python scratch/rebuild_pipeline.py
"""

import json
import sys
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import config
from domain.enums import IssueStatus, RelevanceLevel, FounderAttention, FounderImpact, CommitmentStatus
from domain.models import Event, Observation
from pipeline.issue_tracker import IssueTracker
from pipeline.aggregator import Aggregator
from pipeline.report_generator import ReportGenerator
from pipeline.clustering import ClusteringEngine
from pipeline.org_intelligence import OrgIntelligenceEngine
from storage.event_store import EventStore
from storage.observation_store import ObservationStore
from storage.issue_store import IssueStore
from storage.report_store import ReportStore
from storage.commitment_store import CommitmentStore
from storage.cluster_store import ClusterStore

# Suppress all logging except errors for clean output
import logging
logging.basicConfig(level=logging.ERROR)


def clear_issue_state():
    """Clear existing issue tracker state for a clean rebuild."""
    issues_file = config.ISSUES_OUTPUT_DIR / "issues.json"
    processed_file = config.ISSUES_OUTPUT_DIR / "processed_dates.json"
    commitments_file = config.ISSUES_OUTPUT_DIR / "commitments.json"
    clusters_file = config.CLUSTERS_OUTPUT_DIR / "clusters.json"

    for f in [issues_file, processed_file, commitments_file, clusters_file]:
        if f.exists():
            f.unlink()
            print(f"  Cleared: {f.name}")

    if config.CLUSTERS_OUTPUT_DIR.exists():
        for item in config.CLUSTERS_OUTPUT_DIR.glob("*.json"):
            try:
                item.unlink()
                print(f"  Cleared snapshot: {item.name}")
            except Exception:
                pass


def get_available_dates() -> list[str]:
    """Get all dates with extracted events, in chronological order."""
    events_dir = config.EVENTS_OUTPUT_DIR
    dates = []
    for f in sorted(events_dir.glob("*_events.json")):
        date_str = f.name.replace("_events.json", "")
        dates.append(date_str)
    return dates


def main():
    print("=" * 60)
    print(" FOUNDER INTELLIGENCE PIPELINE — FULL REBUILD")
    print("=" * 60)

    config.create_required_directories()

    # Step 1: Clear existing issue state
    print("\n[Step 1] Clearing existing issue tracker state...")
    clear_issue_state()

    # Step 2: Get available dates
    dates = get_available_dates()
    if not dates:
        print("No extracted event files found in outputs/events/. Run the full pipeline first.")
        sys.exit(1)

    print(f"\n[Step 2] Found {len(dates)} dates to process: {', '.join(dates)}")

    # Initialize stores
    event_store = EventStore()
    observation_store = ObservationStore()
    issue_store = IssueStore()
    report_store = ReportStore()

    # Step 3: Process each date
    print("\n[Step 3] Rebuilding issues, findings, and reports...")

    for date_str in dates:
        print(f"\n  --- Processing: {date_str} ---")

        # Load existing events
        events = event_store.load_events(date_str)
        observations = observation_store.load_observations(date_str)

        print(f"    Events loaded: {len(events)}")
        print(f"    Observations loaded: {len(observations)}")

        # Process through issue tracker
        issue_tracker = IssueTracker(issue_store=issue_store)
        all_issues = issue_tracker.process_events(events, date_str)

        open_count = len(issue_tracker.get_open_issues())
        monitoring_count = len(issue_tracker.get_monitoring_issues())
        resolved_count = len(issue_tracker.get_resolved_issues())

        print(f"    Issues after processing: {len(all_issues)} "
              f"(OPEN={open_count}, MONITORING={monitoring_count}, RESOLVED={resolved_count})")

        # Run aggregation
        all_observations = observation_store.load_all_observations()
        aggregator = Aggregator()
        findings = aggregator.generate_findings(
            events=events,
            issues=all_issues,
            observations=all_observations,
            report_date=date_str,
        )

        print(f"    Intelligence findings: {len(findings)}")

        # Convert YYYY-MM-DD back to DD-MM-YYYY
        parts = date_str.split("-")
        raw_filename = f"{parts[2]}-{parts[1]}-{parts[0]}.json"
        raw_file_path = config.RAW_DATA_DIR / raw_filename
        
        # Load raw messages if file exists
        messages = []
        if raw_file_path.exists():
            from run import load_raw_messages
            try:
                messages = load_raw_messages(raw_file_path)
            except Exception:
                pass

        # NEW STEP: Organizational Intelligence & Commitments
        commitment_store = CommitmentStore()
        cluster_store = ClusterStore()

        # Rebuild does not run LLM extraction, so new_commitments = []
        new_commitments = []
        org_intel_engine = OrgIntelligenceEngine(commitment_store=commitment_store)
        all_commitments = org_intel_engine.process_commitments(new_commitments, messages, date_str)

        clustering_engine = ClusteringEngine(cluster_store=cluster_store)
        issue_clusters = clustering_engine.cluster_issues(all_issues, date_str)

        from pipeline.actionable_generator import ActionableGenerator
        actionable_generator = ActionableGenerator()
        founder_actionables = actionable_generator.generate_actionables(issue_clusters, date_str)

        from pipeline.concern_generator import ConcernGenerator
        concern_generator = ConcernGenerator()
        executive_concerns = concern_generator.generate_concerns(issue_clusters)

        bottleneck_results = org_intel_engine.analyze_personnel_bottlenecks(all_issues)
        knowledge_results = org_intel_engine.analyze_knowledge_concentration(all_issues)

        all_obs = observation_store.load_all_observations()
        team_health_signals = org_intel_engine.analyze_team_health(events, all_obs, all_commitments)
        commitment_risks = org_intel_engine.analyze_commitment_risks(all_commitments)

        serialized_clusters = [json.loads(c.model_dump_json()) for c in issue_clusters]
        serialized_actionables = [json.loads(a.model_dump_json()) for a in founder_actionables]
        serialized_concerns = [json.loads(ec.model_dump_json()) for ec in executive_concerns]

        commitments_due_today = []
        overdue_commitments = []
        for c in all_commitments:
            c_dict = json.loads(c.model_dump_json())
            if c.due_date == date_str and c.status in (CommitmentStatus.OPEN, CommitmentStatus.OVERDUE):
                commitments_due_today.append(c_dict)
            if c.status == CommitmentStatus.OVERDUE:
                overdue_commitments.append(c_dict)

        # Generate report
        report_generator = ReportGenerator()  # No LLM client for rebuild
        founder_report = report_generator.generate_report(
            report_date=date_str,
            events=events,
            observations=observations,
            issues=all_issues,
            findings=findings,
            threads_processed=0,  # Unknown during rebuild
            people_risks=bottleneck_results["people_risks"],
            knowledge_risks=knowledge_results["knowledge_risks"],
            commitment_risks=commitment_risks,
            team_health_signals=team_health_signals,
            top_bottlenecks=bottleneck_results["top_bottlenecks"],
            top_dependency_nodes=bottleneck_results["top_dependency_nodes"],
            commitments_due=commitments_due_today,
            overdue_commitments=overdue_commitments,
            knowledge_concentration=knowledge_results["knowledge_concentration"],
            issue_clusters=serialized_clusters,
            founder_actionables=serialized_actionables,
            high_risk_clusters=serialized_clusters,
            executive_concerns=serialized_concerns,
        )

        report_store.save_report(founder_report, date_str)

    # Step 4: Final validation
    print("\n" + "=" * 60)
    print(" REBUILD COMPLETE — VALIDATION SUMMARY")
    print("=" * 60)

    # Load final state
    final_issues = issue_store.load_issues()

    # Lifecycle audit
    open_issues = [i for i in final_issues if i.status == IssueStatus.OPEN]
    monitoring_issues = [i for i in final_issues if i.status == IssueStatus.MONITORING]
    resolved_issues = [i for i in final_issues if i.status == IssueStatus.RESOLVED]
    closed_issues = [i for i in final_issues if i.status == IssueStatus.CLOSED]

    print(f"\n  --- Issue Lifecycle Audit ---")
    print(f"  Total Issues Created:     {len(final_issues)}")
    print(f"  OPEN:                     {len(open_issues)}")
    print(f"  MONITORING:               {len(monitoring_issues)}")
    print(f"  RESOLVED:                 {len(resolved_issues)}")
    print(f"  CLOSED:                   {len(closed_issues)}")

    # Resolved issues detail
    if resolved_issues:
        print(f"\n  --- Resolved Issues ---")
        for issue in resolved_issues:
            evidence = issue.resolution_summary or "Auto-resolved"
            print(f"    [RESOLVED] {issue.title}")
            print(f"      Evidence: {evidence}")

    # Founder relevance audit
    active_issues = [i for i in final_issues if i.status in (IssueStatus.OPEN, IssueStatus.MONITORING)]
    founder_issues = [i for i in active_issues if i.relevance_level == RelevanceLevel.FOUNDER]
    leadership_issues = [i for i in active_issues if i.relevance_level == RelevanceLevel.LEADERSHIP]
    team_issues = [i for i in active_issues if i.relevance_level == RelevanceLevel.TEAM]
    noise_issues = [i for i in active_issues if i.relevance_level == RelevanceLevel.NOISE]

    print(f"\n  --- Founder Relevance Audit (Active Issues) ---")
    print(f"  FOUNDER:                  {len(founder_issues)}")
    print(f"  LEADERSHIP:               {len(leadership_issues)}")
    print(f"  TEAM:                     {len(team_issues)}")
    print(f"  NOISE:                    {len(noise_issues)}")

    # Attention distribution
    immediate = [i for i in active_issues if i.founder_attention == FounderAttention.IMMEDIATE_ACTION]
    action_req = [i for i in active_issues if i.founder_attention == FounderAttention.ACTION_REQUIRED]
    monitor = [i for i in active_issues if i.founder_attention == FounderAttention.MONITOR]
    fyi = [i for i in active_issues if i.founder_attention == FounderAttention.FYI]

    print(f"\n  --- Attention Distribution (Active Issues) ---")
    print(f"  IMMEDIATE_ACTION:         {len(immediate)}")
    print(f"  ACTION_REQUIRED:          {len(action_req)}")
    print(f"  MONITOR:                  {len(monitor)}")
    print(f"  FYI:                      {len(fyi)}")

    # Impact distribution
    impact_counts = {}
    for issue in active_issues:
        impact = issue.founder_impact.value
        impact_counts[impact] = impact_counts.get(impact, 0) + 1

    print(f"\n  --- Impact Distribution (Active Issues) ---")
    for impact, count in sorted(impact_counts.items(), key=lambda x: -x[1]):
        print(f"  {impact:25s} {count}")

    # Dashboard trust
    print(f"\n  --- Dashboard Trust Assessment ---")
    if len(founder_issues) <= 25 and len(founder_issues) > 0:
        print(f"  Would a founder trust this dashboard? YES")
        print(f"  Reason: {len(founder_issues)} founder-relevant items "
              f"(from {len(final_issues)} total). Signal quality is high.")
    elif len(founder_issues) == 0:
        print(f"  Would a founder trust this dashboard? NEEDS REVIEW")
        print(f"  Reason: No founder-relevant items detected. Classification may be too aggressive.")
    else:
        print(f"  Would a founder trust this dashboard? NEEDS IMPROVEMENT")
        print(f"  Reason: {len(founder_issues)} founder-relevant items is still too many. "
              f"Consider tightening classification.")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
