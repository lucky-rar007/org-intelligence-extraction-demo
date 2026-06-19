"""Entry point to run the Organizational Event Intelligence Extraction Pipeline.

Orchestrates the full pipeline:
1. Load raw Teams messages
2. Build conversation threads
3. Extract events (signals) via LLM
4. Filter → Events + Observations (with founder classification)
5. Persist events and observations
6. Update issue tracker (with lifecycle management & resolution detection)
7. Generate intelligence findings (from events + observations)
8. Generate founder report (structured JSON with prioritization)
9. Persist report
"""

import datetime
import json
import logging
from pathlib import Path
import sys
import time

# Ensure config directory is in path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from domain.enums import RelevanceLevel, FounderAttention, IssueStatus, CommitmentStatus, Severity
from domain.models import Message
from pipeline.thread_builder import ThreadBuilder
from pipeline.event_extractor import EventExtractor
from pipeline.event_filter import EventFilter
from pipeline.issue_tracker import IssueTracker
from pipeline.aggregator import Aggregator
from pipeline.report_generator import ReportGenerator
from pipeline.commitment_extractor import CommitmentExtractor
from pipeline.clustering import ClusteringEngine
from pipeline.org_intelligence import OrgIntelligenceEngine
from storage.event_store import EventStore
from storage.observation_store import ObservationStore
from storage.issue_store import IssueStore
from storage.report_store import ReportStore
from storage.commitment_store import CommitmentStore
from storage.cluster_store import ClusterStore
from llm.llm_client import LLMClient
from utils.date_utils import parse_filename_date, format_date

# Set up simple logging to console
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)


def load_raw_messages(file_path: Path) -> list[Message]:
    """Load raw message logs from Graph API format and convert to Message domain objects."""
    with open(file_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    messages = []
    for raw_msg in raw_data:
        sender = raw_msg.get("from", {}).get("user", {}).get("displayName", "System")
        text = raw_msg.get("body", {}).get("content", "")
        created_time_str = raw_msg.get("createdDateTime")
        if created_time_str.endswith("Z"):
            created_time_str = created_time_str[:-1] + "+00:00"
        timestamp = datetime.datetime.fromisoformat(created_time_str)

        msg = Message(
            id=raw_msg.get("id"),
            sender=sender,
            text=text,
            timestamp=timestamp,
            reply_to=raw_msg.get("replyToId")
        )
        messages.append(msg)

    return messages


def detect_local_ollama_model() -> None:
    """Detect local Ollama models and align config.OLLAMA_MODEL to prevent missing model errors."""
    try:
        import subprocess
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True)
        output = result.stdout
        # If llama3.1:8b exists but default llama3.1:8b-instruct does not, override to llama3.1:8b
        if "llama3.1:8b" in output and "llama3.1:8b-instruct" not in output:
            config.OLLAMA_MODEL = "llama3.1:8b"
    except Exception:
        pass


def main() -> None:
    total_start = time.time()
    print("=" * 60)
    print(" FOUNDER INTELLIGENCE PIPELINE ")
    print("=" * 60)

    # 0. Detect local Ollama model to avoid model conflicts
    detect_local_ollama_model()

    # 1. Scan RAW data folder
    raw_dir = config.RAW_DATA_DIR
    if not raw_dir.exists():
        print(f"Error: Raw data directory '{raw_dir}' does not exist.")
        sys.exit(1)

    raw_files = sorted(list(raw_dir.glob("*.json")))
    if not raw_files:
        print(f"No raw JSON log files found in '{raw_dir}'.")
        sys.exit(1)

    # 2. Interactive or command-line file selection
    selected_idx = -1
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.isdigit():
            val = int(arg)
            if 1 <= val <= len(raw_files):
                selected_idx = val - 1
        else:
            for idx, file_path in enumerate(raw_files):
                if file_path.name == arg:
                    selected_idx = idx
                    break
        if selected_idx == -1:
            print(f"Error: Specified file/index '{arg}' is invalid.")
            sys.exit(1)
    else:
        print("\nAvailable raw conversation log files:")
        for idx, file_path in enumerate(raw_files):
            print(f"  [{idx + 1}] {file_path.name}")

        while True:
            try:
                choice = input(f"\nSelect a file to run (1-{len(raw_files)}): ").strip()
                if not choice:
                    continue
                choice_num = int(choice)
                if 1 <= choice_num <= len(raw_files):
                    selected_idx = choice_num - 1
                    break
                print(f"Please enter a number between 1 and {len(raw_files)}.")
            except ValueError:
                print("Invalid input. Please enter a valid number.")

    selected_file = raw_files[selected_idx]
    print(f"\nSelected target: {selected_file.name}")

    # Derive report date from filename
    try:
        report_date_obj = parse_filename_date(selected_file.name)
        report_date = format_date(report_date_obj)
    except ValueError:
        # Fallback to today's date if filename doesn't match expected format
        report_date_obj = datetime.date.today()
        report_date = format_date(report_date_obj)

    # Ensure required dirs exist
    config.create_required_directories()

    # Initialize stores
    event_store = EventStore()
    observation_store = ObservationStore()
    issue_store = IssueStore()
    report_store = ReportStore()

    # ================================================================
    # STEP 1: Load Raw Messages
    # ================================================================
    t_start = time.time()
    print(f"\n[Step 1/8] Parsing raw logs...")
    try:
        messages = load_raw_messages(selected_file)
        print(f"  Parsed {len(messages)} messages.")
    except Exception as e:
        print(f"Error parsing raw messages: {e}")
        sys.exit(1)
    print(f"  Step 1 took {time.time() - t_start:.2f}s")

    # ================================================================
    # STEP 2: Reconstruct Threads
    # ================================================================
    t_start = time.time()
    print(f"\n[Step 2/8] Reconstructing conversation threads...")
    builder = ThreadBuilder()
    threads = builder.build_threads(messages)

    # Save to data/processed/
    processed_file = config.PROCESSED_DATA_DIR / selected_file.name
    threads_data = [json.loads(t.model_dump_json()) for t in threads]
    with open(processed_file, "w", encoding="utf-8") as f:
        json.dump(threads_data, f, indent=2)

    print(f"  Processed threads: {len(threads)}")
    print(f"  Reconstructed threads saved to: data/processed/{selected_file.name}")
    threads_processed = len(threads)
    print(f"  Step 2 took {time.time() - t_start:.2f}s")

    # ================================================================
    # STEP 3: Extract Events (Signals) using LLM
    # ================================================================
    t_start = time.time()
    print(f"\n[Step 3/8] Extracting organizational signals via Ollama LLM...")
    try:
        print(f"  Verifying local Ollama model '{config.OLLAMA_MODEL}'...")
        llm_client = LLMClient()
        extractor = EventExtractor(llm_client=llm_client)

        print(f"  Analyzing threads with model '{config.OLLAMA_MODEL}' (this may take a moment)...")
        all_signals = extractor.extract_from_threads(threads)
        print(f"  Total signals extracted: {len(all_signals)}")

    except Exception as e:
        print(f"Error running event extraction: {e}")
        sys.exit(1)
    print(f"  Step 3 took {time.time() - t_start:.2f}s")

    # ================================================================
    # STEP 4: Filter → Events + Observations (with Founder Classification)
    # ================================================================
    t_start = time.time()
    print(f"\n[Step 4/8] Classifying signals into Events and Observations...")
    event_filter = EventFilter()
    filter_result = event_filter.filter_events(all_signals)

    events = filter_result.events
    observations = filter_result.observations

    # Count founder-relevant events
    founder_events = [e for e in events if e.relevance_level == RelevanceLevel.FOUNDER]
    leadership_events = [e for e in events if e.relevance_level == RelevanceLevel.LEADERSHIP]

    print(f"  Actionable events: {len(events)}")
    print(f"    -> Founder-relevant: {len(founder_events)}")
    print(f"    -> Leadership-relevant: {len(leadership_events)}")
    print(f"  Observations (weak signals retained): {len(observations)}")
    print(f"  Step 4 took {time.time() - t_start:.2f}s")

    # ================================================================
    # STEP 5: Persist Events and Observations
    # ================================================================
    t_start = time.time()
    print(f"\n[Step 5/8] Persisting events and observations...")
    event_store.save_events(events, report_date)
    observation_store.save_observations(observations, report_date)

    print(f"  Events saved to: outputs/events/{report_date}_events.json")
    print(f"  Observations saved to: outputs/observations/{report_date}_observations.json")
    print(f"  Step 5 took {time.time() - t_start:.2f}s")

    # ================================================================
    # STEP 6: Update Issue Tracker (with Lifecycle Management)
    # ================================================================
    t_start = time.time()
    print(f"\n[Step 6/8] Updating issue tracker (lifecycle + resolution detection)...")
    issue_tracker = IssueTracker(issue_store=issue_store)
    all_issues = issue_tracker.process_events(events, report_date, threads=threads)

    open_issues = issue_tracker.get_open_issues()
    monitoring_issues = issue_tracker.get_monitoring_issues()
    resolved_issues = issue_tracker.get_resolved_issues()
    founder_issues = [
        i for i in all_issues
        if i.status in (IssueStatus.OPEN, IssueStatus.MONITORING)
        and i.relevance_level == RelevanceLevel.FOUNDER
    ]

    print(f"  Total tracked issues: {len(all_issues)}")
    print(f"    -> OPEN: {len(open_issues)}")
    print(f"    -> MONITORING: {len(monitoring_issues)}")
    print(f"    -> RESOLVED: {len(resolved_issues)}")
    print(f"    -> Founder-relevant (active): {len(founder_issues)}")
    print(f"  Step 6 took {time.time() - t_start:.2f}s")

    # ================================================================
    # STEP 7: Generate Intelligence Findings
    # ================================================================
    t_start = time.time()
    print(f"\n[Step 7/8] Generating intelligence findings...")

    # Load historical observations for cross-day aggregation
    all_observations = observation_store.load_all_observations()

    aggregator = Aggregator()
    findings = aggregator.generate_findings(
        events=events,
        issues=all_issues,
        observations=all_observations,
        report_date=report_date,
    )

    print(f"  Intelligence findings generated: {len(findings)}")
    for finding in findings:
        print(f"    - [{finding.severity.value}] [{finding.founder_attention.value}] {finding.title}")
    print(f"  Step 7 took {time.time() - t_start:.2f}s")

    # ================================================================
    # STEP 8: Generate Founder Report
    # ================================================================
    t_start = time.time()
    print(f"\n[Step 8/8] Generating founder report...")
    report_generator = ReportGenerator(llm_client=llm_client)

    commitment_store = CommitmentStore()
    cluster_store = ClusterStore()

    commitment_extractor = CommitmentExtractor(llm_client=llm_client)
    new_commitments = commitment_extractor.extract_commitments(messages, report_date)

    org_intel_engine = OrgIntelligenceEngine(commitment_store=commitment_store)
    all_commitments = org_intel_engine.process_commitments(new_commitments, messages, report_date)

    clustering_engine = ClusteringEngine(cluster_store=cluster_store)
    issue_clusters = clustering_engine.cluster_issues(all_issues, report_date)

    from pipeline.actionable_generator import ActionableGenerator
    actionable_generator = ActionableGenerator()
    founder_actionables = actionable_generator.generate_actionables(issue_clusters, report_date)

    from pipeline.concern_generator import ConcernGenerator
    concern_generator = ConcernGenerator()
    executive_concerns = concern_generator.generate_concerns(issue_clusters)

    bottleneck_results = org_intel_engine.analyze_personnel_bottlenecks(all_issues)
    knowledge_results = org_intel_engine.analyze_knowledge_concentration(all_issues)

    all_obs = observation_store.load_all_observations()
    team_health_signals = org_intel_engine.analyze_team_health(events, all_obs, all_commitments)
    commitment_risks = org_intel_engine.analyze_commitment_risks(all_commitments)

    serialized_clusters = [json.loads(c.model_dump_json()) for c in issue_clusters]
    serialized_high_risk_clusters = [
        json.loads(c.model_dump_json())
        for c in issue_clusters
        if c.severity in (Severity.HIGH, Severity.CRITICAL)
    ]
    serialized_actionables = [json.loads(a.model_dump_json()) for a in founder_actionables]
    serialized_concerns = [json.loads(ec.model_dump_json()) for ec in executive_concerns]

    commitments_due_today = []
    overdue_commitments = []
    for c in all_commitments:
        c_dict = json.loads(c.model_dump_json())
        if c.due_date == report_date and c.status in (CommitmentStatus.OPEN, CommitmentStatus.OVERDUE):
            commitments_due_today.append(c_dict)
        if c.status == CommitmentStatus.OVERDUE:
            overdue_commitments.append(c_dict)

    founder_report = report_generator.generate_report(
        report_date=report_date,
        events=events,
        observations=observations,
        issues=all_issues,
        findings=findings,
        threads_processed=threads_processed,
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
        high_risk_clusters=serialized_high_risk_clusters,
        executive_concerns=serialized_concerns,
    )

    # Persist the report
    report_store.save_report(founder_report, report_date)
    print(f"  Founder report saved to: outputs/reports/{report_date}_founder_report.json")
    print(f"  Step 8 took {time.time() - t_start:.2f}s")

    # ================================================================
    # FINAL SUMMARY
    # ================================================================
    print("\n" + "=" * 60)
    print(" PIPELINE RUN COMPLETED SUCCESSFULLY ")
    print("=" * 60)
    print(f"\n  Report Date:              {report_date}")
    print(f"  Threads Processed:        {threads_processed}")
    print(f"  Signals Extracted:        {len(all_signals)}")
    print(f"  Actionable Events:        {len(events)}")
    print(f"  Observations:             {len(observations)}")
    print(f"  --- Issue Lifecycle ---")
    print(f"  Total Issues:             {len(all_issues)}")
    print(f"  OPEN:                     {len(open_issues)}")
    print(f"  MONITORING:               {len(monitoring_issues)}")
    print(f"  RESOLVED:                 {len(resolved_issues)}")
    print(f"  --- Founder Relevance ---")
    print(f"  Founder-Relevant (active):{len(founder_issues)}")
    print(f"  Intelligence Findings:    {len(findings)}")
    print(f"  Total pipeline time:      {time.time() - total_start:.2f}s")
    print(f"\n  Report: outputs/reports/{report_date}_founder_report.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
