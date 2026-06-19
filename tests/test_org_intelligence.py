import datetime
from domain.enums import EventType, IssueStatus, Severity, CommitmentStatus
from domain.models import Event, Issue, Commitment, Message, Observation
from domain.enums import ObservationType
from pipeline.issue_tracker import normalize_issue_title
from pipeline.clustering import ClusteringEngine, CLUSTER_MAPPINGS
from pipeline.org_intelligence import OrgIntelligenceEngine, normalize_name
from storage.commitment_store import CommitmentStore
from storage.cluster_store import ClusterStore


class MockCommitmentStore(CommitmentStore):
    def __init__(self):
        self._commitments = []

    def load_commitments(self):
        return list(self._commitments)

    def save_commitments(self, commitments):
        self._commitments = list(commitments)


class MockClusterStore(ClusterStore):
    def __init__(self):
        self._clusters = []

    def load_clusters(self):
        return list(self._clusters)

    def save_clusters(self, clusters):
        self._clusters = list(clusters)

    def save_daily_snapshot(self, clusters, report_date):
        pass


def test_title_normalization():
    """Verify title normalization strips low-information words."""
    assert normalize_issue_title("Payment Gateway Deployment Delay") == "payment gateway deployment"
    assert normalize_issue_title("Payment Gateway Build Failure") == "payment gateway build"
    assert normalize_issue_title("Client ABC API Endpoint Delay") == "client abc api endpoint"
    assert normalize_issue_title("Redis Bug and Ticket Follow-Up") == "redis and"


def test_name_normalization():
    """Verify participant name normalization."""
    assert normalize_name("Siddharth Rao") == "Siddharth"
    assert normalize_name("Ananya Iyer") == "Ananya"
    assert normalize_name("Karan Verma") == "Karan"
    assert normalize_name("Neha Gupta") == "Neha"
    assert normalize_name("Rohan Mehta") == "Rohan"
    assert normalize_name("siddharth") == "Siddharth"


def test_root_cause_clustering():
    """Verify issues get grouped under clusters correctly."""
    store = MockClusterStore()
    engine = ClusteringEngine(cluster_store=store)

    now = datetime.datetime.now(datetime.timezone.utc)
    issue1 = Issue(
        id="iss-1",
        title="Payment Gateway Deployment Delay",
        summary="Delay in gateway deployment.",
        severity=Severity.HIGH,
        status=IssueStatus.OPEN,
        first_seen=now,
        last_seen=now,
        occurrence_count=1,
        linked_event_ids=["evt-1"]
    )
    issue2 = Issue(
        id="iss-2",
        title="Payment Gateway Build Failure",
        summary="Build is failing on Paytm SDK integration.",
        severity=Severity.CRITICAL,
        status=IssueStatus.OPEN,
        first_seen=now,
        last_seen=now,
        occurrence_count=1,
        linked_event_ids=["evt-2"]
    )
    issue3 = Issue(
        id="iss-3",
        title="Client XYZ API Delay",
        summary="Sla breached for Client XYZ.",
        severity=Severity.MEDIUM,
        status=IssueStatus.RESOLVED,
        first_seen=now,
        last_seen=now,
        occurrence_count=1,
        linked_event_ids=["evt-3"]
    )

    clusters = engine.cluster_issues([issue1, issue2, issue3])
    # Payment gateway issues should group under "Payment Gateway Rollout Problems"
    gateway_cluster = next((c for c in clusters if "Payment Gateway" in c.cluster_title), None)
    assert gateway_cluster is not None
    assert len(gateway_cluster.related_issue_ids) == 2
    assert "iss-1" in gateway_cluster.related_issue_ids
    assert "iss-2" in gateway_cluster.related_issue_ids
    assert gateway_cluster.severity == Severity.CRITICAL
    assert gateway_cluster.status == IssueStatus.OPEN

    client_cluster = next((c for c in clusters if "Client XYZ" in c.cluster_title), None)
    assert client_cluster is not None
    assert len(client_cluster.related_issue_ids) == 1
    assert "iss-3" in client_cluster.related_issue_ids
    assert client_cluster.status == IssueStatus.RESOLVED


def test_personnel_bottleneck_detection():
    """Verify personnel bottleneck / SPOF risk checks."""
    engine = OrgIntelligenceEngine()

    now = datetime.datetime.now(datetime.timezone.utc)
    # Siddharth is involved in all critical incidents
    issues = [
        Issue(
            id="iss-1",
            title="Redis CPU Spike - Siddharth",
            summary="Siddharth fixing the redis spike.",
            severity=Severity.CRITICAL,
            status=IssueStatus.OPEN,
            first_seen=now,
            last_seen=now,
            occurrence_count=1,
            affected_team="Siddharth"
        ),
        Issue(
            id="iss-2",
            title="Payment Gateway Down - Siddharth",
            summary="Siddharth Rao debugging paytm checkout.",
            severity=Severity.HIGH,
            status=IssueStatus.OPEN,
            first_seen=now,
            last_seen=now,
            occurrence_count=1,
            affected_team="Siddharth"
        )
    ]

    results = engine.analyze_personnel_bottlenecks(issues)
    assert "Siddharth" in results["top_bottlenecks"]
    assert len(results["people_risks"]) == 1
    assert results["people_risks"][0]["person"] == "Siddharth"
    assert results["people_risks"][0]["concentration_percentage"] == 100


def test_knowledge_concentration():
    """Verify technical silo / knowledge concentration detection."""
    engine = OrgIntelligenceEngine()

    now = datetime.datetime.now(datetime.timezone.utc)
    # Redis issues involving Siddharth
    issues = [
        Issue(
            id="iss-1",
            title="Redis CPU Spike",
            summary="Redis connection pool overflow. Siddharth is checking.",
            severity=Severity.CRITICAL,
            status=IssueStatus.OPEN,
            first_seen=now,
            last_seen=now,
            occurrence_count=1
        ),
        Issue(
            id="iss-2",
            title="Redis Cache Key Expiry",
            summary="Redis key not expiry. Siddharth looking at it.",
            severity=Severity.MEDIUM,
            status=IssueStatus.OPEN,
            first_seen=now,
            last_seen=now,
            occurrence_count=1
        )
    ]

    results = engine.analyze_knowledge_concentration(issues)
    assert len(results["knowledge_risks"]) == 1
    assert results["knowledge_risks"][0]["subsystem"] == "Redis"
    assert results["knowledge_risks"][0]["primary_engineer"] == "Siddharth"
    assert results["knowledge_risks"][0]["concentration_percentage"] == 100


def test_commitment_lifecycle():
    """Verify commitment transitions from OPEN to COMPLETED or OVERDUE."""
    store = MockCommitmentStore()
    engine = OrgIntelligenceEngine(commitment_store=store)

    c1 = Commitment(
        commitment_id="cmt-1",
        owner="Siddharth",
        description="deploy the redis fix",
        created_date="2026-06-11",
        due_date="2026-06-12",
        status=CommitmentStatus.OPEN
    )
    c2 = Commitment(
        commitment_id="cmt-2",
        owner="Ananya",
        description="send client demo updates",
        created_date="2026-06-11",
        due_date="2026-06-11",
        status=CommitmentStatus.OPEN
    )

    store._commitments = [c1, c2]

    # Day 1: 2026-06-11
    # Ananya completes her task. Siddharth's due date is tomorrow.
    messages_day1 = [
        Message(
            id="m-1",
            sender="Ananya Iyer",
            text="Hi all, I have merged the client demo changes and v1.0.1 is pushed. PR is merged.",
            timestamp=datetime.datetime(2026, 6, 11, 15, 0)
        )
    ]

    commitments = engine.process_commitments([], messages_day1, "2026-06-11")
    updated_c1 = next(c for c in commitments if c.commitment_id == "cmt-1")
    updated_c2 = next(c for c in commitments if c.commitment_id == "cmt-2")

    # c2 is completed because "demo" & completion keywords matched
    assert updated_c2.status == CommitmentStatus.COMPLETED
    assert updated_c1.status == CommitmentStatus.OPEN

    # Day 2: 2026-06-12
    # Siddharth completes his task
    messages_day2 = [
        Message(
            id="m-2",
            sender="Siddharth Rao",
            text="redis client bug is fixed and deployed.",
            timestamp=datetime.datetime(2026, 6, 12, 10, 0)
        )
    ]
    commitments_day2 = engine.process_commitments([], messages_day2, "2026-06-12")
    updated_c1_day2 = next(c for c in commitments_day2 if c.commitment_id == "cmt-1")
    assert updated_c1_day2.status == CommitmentStatus.COMPLETED

    # Test Overdue
    c3 = Commitment(
        commitment_id="cmt-3",
        owner="Karan",
        description="build android apk",
        created_date="2026-06-11",
        due_date="2026-06-11",
        status=CommitmentStatus.OPEN
    )
    store._commitments = [c3]
    commitments_day3 = engine.process_commitments([], [], "2026-06-12")
    updated_c3 = next(c for c in commitments_day3 if c.commitment_id == "cmt-3")
    assert updated_c3.status == CommitmentStatus.OVERDUE
