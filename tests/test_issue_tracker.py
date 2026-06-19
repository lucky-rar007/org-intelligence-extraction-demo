import datetime
from zoneinfo import ZoneInfo
from domain.enums import EventType, IssueStatus, Severity, RelevanceLevel
from domain.models import Event, Issue, Thread, Message
from pipeline.issue_tracker import IssueTracker
from pipeline.resolution_detector import ResolutionDetector
from storage.issue_store import IssueStore


class MockIssueStore(IssueStore):
    """InMemory mock of IssueStore to avoid filesystem dependence during tests."""
    def __init__(self):
        self._issues = []
        self._processed = set()

    def load_issues(self) -> list[Issue]:
        return list(self._issues)

    def save_issues(self, issues: list[Issue]) -> None:
        self._issues = list(issues)

    def get_processed_dates(self) -> set[str]:
        return self._processed

    def mark_date_processed(self, date_str: str) -> None:
        self._processed.add(date_str)

    def is_date_processed(self, date_str: str) -> bool:
        return date_str in self._processed


def test_resolution_detector_basic():
    """Verify that ResolutionDetector handles strong and weak indicators correctly."""
    detector = ResolutionDetector()

    # Strong resolution event
    evt_resolved = Event(
        id="evt-1",
        title="Payment Gateway Fix Verified",
        description="The payment gateway issue is successfully resolved and verified in production.",
        event_type=EventType.PRODUCTION_INCIDENT,
        severity=Severity.HIGH,
        source_thread_id="t-1",
        confidence_score=0.9,
        created_at=datetime.datetime.now(datetime.timezone.utc)
    )
    result = detector.detect_resolution(evt_resolved)
    assert result.is_resolution is True
    assert result.target_status == IssueStatus.RESOLVED
    assert result.resolution_confidence >= 0.8
    assert "resolved" in result.matched_keywords

    # Monitoring event
    evt_monitoring = Event(
        id="evt-2",
        title="Webhook Patch Deployed",
        description="We are currently monitoring production metrics for webhooks.",
        event_type=EventType.PRODUCTION_INCIDENT,
        severity=Severity.HIGH,
        source_thread_id="t-2",
        confidence_score=0.9,
        created_at=datetime.datetime.now(datetime.timezone.utc)
    )
    result_mon = detector.detect_resolution(evt_monitoring)
    assert result_mon.is_resolution is True
    assert result_mon.target_status == IssueStatus.MONITORING
    assert result_mon.resolution_confidence >= 0.4
    assert result_mon.resolution_confidence < 0.8

    # Weak language downgrade
    evt_weak = Event(
        id="evt-3",
        title="Payment Gateway resolved?",
        description="The fix was pushed, should be okay now let's see.",
        event_type=EventType.PRODUCTION_INCIDENT,
        severity=Severity.HIGH,
        source_thread_id="t-3",
        confidence_score=0.9,
        created_at=datetime.datetime.now(datetime.timezone.utc)
    )
    result_weak = detector.detect_resolution(evt_weak)
    assert result_weak.is_resolution is True
    # Down graded from RESOLVED to MONITORING because of "should be" / "let's see"
    assert result_weak.target_status == IssueStatus.MONITORING


def test_resolution_detector_with_messages():
    """Verify that thread messages are parsed and used as evidence for resolution."""
    detector = ResolutionDetector()

    event = Event(
        id="evt-1",
        title="CORS issue update",
        description="CORS issue is discussed.",
        event_type=EventType.ENVIRONMENT_ISSUE,
        severity=Severity.MEDIUM,
        source_thread_id="t-1",
        confidence_score=0.9,
        created_at=datetime.datetime.now(datetime.timezone.utc)
    )

    thread = Thread(
        id="t-1",
        date=datetime.date(2026, 6, 11),
        participants=["Ananya", "Rohan"],
        messages=[
            Message(id="msg-1", sender="Rohan", text="Still seeing CORS error.", timestamp=datetime.datetime.now(datetime.timezone.utc)),
            Message(id="msg-2", sender="Ananya", text="Deploying v2.1.1 now.", timestamp=datetime.datetime.now(datetime.timezone.utc)),
            Message(id="msg-3", sender="Ananya", text="Build v2.1.1 deployed successfully. Issue gone.", timestamp=datetime.datetime.now(datetime.timezone.utc))
        ]
    )

    result = detector.detect_resolution(event, thread)
    assert result.is_resolution is True
    assert result.target_status == IssueStatus.RESOLVED
    assert result.evidence_message_id == "msg-3"
    assert result.evidence_author == "Ananya"
    assert "issue gone" in result.matched_keywords


def test_issue_matching_by_entity():
    """Verify that issue matching correctly pairs resolutions with issues based on entities and similarity."""
    store = MockIssueStore()
    tracker = IssueTracker(issue_store=store)

    # Pre-populate tracker with some open issues
    open_issue = Issue(
        id="iss-1",
        title="Payment Gateway Delay",
        summary="Payment gateway responses are slow.",
        severity=Severity.HIGH,
        status=IssueStatus.OPEN,
        first_seen=datetime.datetime(2026, 6, 11, 10, 0, tzinfo=datetime.timezone.utc),
        last_seen=datetime.datetime(2026, 6, 11, 10, 0, tzinfo=datetime.timezone.utc),
        occurrence_count=1,
        last_updated=datetime.datetime(2026, 6, 11, 10, 0, tzinfo=datetime.timezone.utc)
    )
    tracker._issues.append(open_issue)

    # Create a resolution event that should match
    res_event = Event(
        id="evt-res",
        title="Payment Gateway Deployment Fixed",
        description="The payment gateway release is live and working now.",
        event_type=EventType.PRODUCTION_INCIDENT,
        severity=Severity.HIGH,
        source_thread_id="t-2",
        confidence_score=0.9,
        created_at=datetime.datetime(2026, 6, 11, 12, 0, tzinfo=datetime.timezone.utc)
    )

    matched = tracker._find_matching_issue_for_resolution(res_event)
    assert matched is not None
    assert matched.id == "iss-1"


def test_state_machine_and_safety_rules():
    """Test state machine lifecycle transitions and safety requirements."""
    store = MockIssueStore()
    tracker = IssueTracker(issue_store=store)

    # 1. Transition OPEN -> MONITORING
    issue = Issue(
        id="iss-1",
        title="Client ABC CORS Issue",
        summary="CORS errors blocking Client ABC.",
        severity=Severity.HIGH,
        status=IssueStatus.OPEN,
        first_seen=datetime.datetime(2026, 6, 11, 10, 0, tzinfo=datetime.timezone.utc),
        last_seen=datetime.datetime(2026, 6, 11, 10, 0, tzinfo=datetime.timezone.utc),
        occurrence_count=1,
        last_updated=datetime.datetime(2026, 6, 11, 10, 0, tzinfo=datetime.timezone.utc)
    )
    tracker._issues.append(issue)

    # Event for monitoring
    evt_monitoring = Event(
        id="evt-mon",
        title="Client ABC Sync Fix Deployed to Staging",
        description="Hotfix deployed. We are monitoring staging logs.",
        event_type=EventType.ENVIRONMENT_ISSUE,
        severity=Severity.MEDIUM,
        source_thread_id="t-1",
        confidence_score=0.9,
        created_at=datetime.datetime(2026, 6, 11, 11, 0, tzinfo=datetime.timezone.utc)
    )

    tracker.process_events([evt_monitoring], "2026-06-11")
    assert issue.status == IssueStatus.MONITORING
    assert len(issue.status_history) == 1
    assert issue.status_history[0]["to"] == "MONITORING"
    assert issue.days_open == 0

    # 2. Transition MONITORING -> RESOLVED
    evt_resolved = Event(
        id="evt-res",
        title="Client ABC Sync Fix Verified",
        description="Staging looks healthy now. Verified fixed by client.",
        event_type=EventType.CLIENT_REQUEST,
        severity=Severity.MEDIUM,
        source_thread_id="t-2",
        confidence_score=0.9,
        created_at=datetime.datetime(2026, 6, 12, 11, 0, tzinfo=datetime.timezone.utc)
    )

    tracker.process_events([evt_resolved], "2026-06-12")
    assert issue.status == IssueStatus.RESOLVED
    assert issue.resolved_at is not None
    assert issue.resolved_at.date() == datetime.date(2026, 6, 12)
    assert issue.resolved_by_event_id == "evt-res"
    assert issue.days_open == 1  # 2026-06-12 - 2026-06-11 = 1 day

    # 3. Never transition backwards
    evt_regressed = Event(
        id="evt-reg",
        title="Client ABC Sync Fix Regression",
        description="The CORS issue is back again on staging.",
        event_type=EventType.ENVIRONMENT_ISSUE,
        severity=Severity.HIGH,
        source_thread_id="t-3",
        confidence_score=0.9,
        created_at=datetime.datetime(2026, 6, 13, 11, 0, tzinfo=datetime.timezone.utc)
    )

    # Processing this regression event should NOT match the resolved issue to modify its status
    tracker.process_events([evt_regressed], "2026-06-13")
    # Clean check: original issue remains RESOLVED
    assert issue.status == IssueStatus.RESOLVED
    
    # A NEW issue is created instead of updating the resolved one
    active_issues = tracker.get_active_issues()
    assert len(active_issues) == 1
    assert active_issues[0].title == "Client ABC Sync Fix Regression"
    assert active_issues[0].status == IssueStatus.OPEN


def test_no_issue_created_for_unmatched_resolution_event():
    """Verify that resolution events with no matching active issues do not create new issues."""
    store = MockIssueStore()
    tracker = IssueTracker(issue_store=store)

    evt_unmatched_res = Event(
        id="evt-unmatched",
        title="Old legacy database migration completed successfully",
        description="Successfully finished the archive run.",
        event_type=EventType.RELEASE_DELAY,
        severity=Severity.LOW,
        source_thread_id="t-99",
        confidence_score=0.9,
        created_at=datetime.datetime.now(datetime.timezone.utc)
    )

    tracker.process_events([evt_unmatched_res], "2026-06-11")
    # Tracker should remain empty — no new issue was created
    assert len(tracker._issues) == 0
