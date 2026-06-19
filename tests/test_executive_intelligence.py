import datetime
from domain.enums import EventType, IssueStatus, Severity, CommitmentStatus
from domain.models import Event, Issue, IssueCluster, FounderActionable
from pipeline.clustering import ClusteringEngine
from pipeline.actionable_generator import ActionableGenerator
from storage.cluster_store import ClusterStore


class MockClusterStore(ClusterStore):
    def __init__(self):
        self._clusters = []

    def load_clusters(self):
        return list(self._clusters)

    def save_clusters(self, clusters):
        self._clusters = list(clusters)

    def save_daily_snapshot(self, clusters, report_date):
        pass


def test_single_issue_clustering():
    """Verify that every issue gets clustered, even if it's a single issue."""
    store = MockClusterStore()
    engine = ClusteringEngine(cluster_store=store)

    now = datetime.datetime.now(datetime.timezone.utc)
    issue = Issue(
        id="iss-unique",
        title="Unusual CPU Spike on Auth Microservice",
        summary="Auth service memory leak.",
        severity=Severity.HIGH,
        status=IssueStatus.OPEN,
        first_seen=now,
        last_seen=now,
        occurrence_count=1,
        linked_event_ids=["evt-99"]
    )

    clusters = engine.cluster_issues([issue], report_date="2026-06-19")
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.cluster_id == "cls-iss-unique"
    assert "Auth Microservice" in cluster.title
    assert "iss-unique" in cluster.supporting_issue_ids
    assert cluster.status == IssueStatus.OPEN


def test_cluster_status_and_severity_derivation():
    """Verify cluster status and severity are derived correctly from children."""
    store = MockClusterStore()
    engine = ClusteringEngine(cluster_store=store)

    now = datetime.datetime.now(datetime.timezone.utc)
    issues = [
        Issue(
            id="iss-1",
            title="Redis key failure",
            summary="Redis cache failed.",
            severity=Severity.LOW,
            status=IssueStatus.MONITORING,
            first_seen=now,
            last_seen=now,
            occurrence_count=1,
            linked_event_ids=["evt-1"]
        ),
        Issue(
            id="iss-2",
            title="Redis Connection Pool Exhausted",
            summary="Too many open handles.",
            severity=Severity.CRITICAL,
            status=IssueStatus.OPEN,
            first_seen=now,
            last_seen=now,
            occurrence_count=3,
            linked_event_ids=["evt-2"]
        )
    ]

    clusters = engine.cluster_issues(issues, report_date="2026-06-19")
    redis_cluster = next(c for c in clusters if "Redis" in c.title)
    assert redis_cluster.status == IssueStatus.OPEN  # because iss-2 is OPEN
    assert redis_cluster.severity == Severity.CRITICAL  # because iss-2 is CRITICAL
    assert redis_cluster.occurrence_count == 4


def test_cluster_days_open():
    """Verify days_open is relative to earliest child issue's first_seen date."""
    store = MockClusterStore()
    engine = ClusteringEngine(cluster_store=store)

    # First seen is 5 days ago
    first_seen = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5)
    last_seen = datetime.datetime.now(datetime.timezone.utc)

    issue = Issue(
        id="iss-1",
        title="Redis Cache Key Failure",
        summary="Fails on expiry.",
        severity=Severity.HIGH,
        status=IssueStatus.OPEN,
        first_seen=first_seen,
        last_seen=last_seen,
        occurrence_count=1,
        linked_event_ids=["evt-1"]
    )

    # Report date is today
    report_date = datetime.date.today().isoformat()
    clusters = engine.cluster_issues([issue], report_date=report_date)
    assert clusters[0].days_open >= 5


def test_trend_detection():
    """Verify that cluster trends transition correctly (NEW, STABLE, WORSENING, RESOLVED)."""
    store = MockClusterStore()
    engine = ClusteringEngine(cluster_store=store)

    now = datetime.datetime.now(datetime.timezone.utc)
    issue1 = Issue(
        id="iss-1",
        title="Redis CPU Spike",
        summary="Heavy load.",
        severity=Severity.HIGH,
        status=IssueStatus.OPEN,
        first_seen=now,
        last_seen=now,
        occurrence_count=1,
        linked_event_ids=["evt-1"]
    )

    # Day 1: New cluster
    clusters_day1 = engine.cluster_issues([issue1], report_date="2026-06-19")
    assert clusters_day1[0].trend == "NEW"

    # Save to mock store to represent historical state
    store.save_clusters(clusters_day1)

    # Day 2: Same issue, no changes -> STABLE
    clusters_day2 = engine.cluster_issues([issue1], report_date="2026-06-20")
    assert clusters_day2[0].trend == "STABLE"

    # Save Day 2 state
    store.save_clusters(clusters_day2)

    # Day 3: New issue added -> WORSENING
    issue2 = Issue(
        id="iss-2",
        title="Redis Connection Failure",
        summary="Auth failure.",
        severity=Severity.HIGH,
        status=IssueStatus.OPEN,
        first_seen=now,
        last_seen=now,
        occurrence_count=1,
        linked_event_ids=["evt-2"]
    )
    clusters_day3 = engine.cluster_issues([issue1, issue2], report_date="2026-06-21")
    assert clusters_day3[0].trend == "WORSENING"

    # Save Day 3 state
    store.save_clusters(clusters_day3)

    # Day 4: Issues resolved -> RESOLVED
    issue1_resolved = issue1.model_copy(update={"status": IssueStatus.RESOLVED})
    issue2_resolved = issue2.model_copy(update={"status": IssueStatus.RESOLVED})
    clusters_day4 = engine.cluster_issues([issue1_resolved, issue2_resolved], report_date="2026-06-22")
    assert clusters_day4[0].trend == "RESOLVED"


def test_actionables_and_evidence_chain():
    """Verify that FounderActionable is generated from clusters with complete evidence chain."""
    now = datetime.datetime.now(datetime.timezone.utc)
    cluster = IssueCluster(
        cluster_id="cls-payment-gateway",
        title="Payment Gateway Rollout Problems",
        summary="Payment gateway build failure and delay.",
        business_area="Finance / Checkout",
        severity=Severity.CRITICAL,
        status=IssueStatus.OPEN,
        days_open=3,
        first_seen=now,
        last_seen=now,
        occurrence_count=5,
        supporting_issue_ids=["iss-1", "iss-2"],
        supporting_event_ids=["evt-1", "evt-2"],
        recommended_action="Review release process.",
        owner_candidates=["Aditya", "Vikram"],
        trend="NEW",
        risk_type="REVENUE_RISK",
        source_channels=["engineering"],
        source_teams=["Core Eng"],
        confidence_score=0.9,
        timeline=[]
    )

    generator = ActionableGenerator()
    actionables = generator.generate_actionables([cluster], report_date="2026-06-19")

    assert len(actionables) == 1
    act = actionables[0]
    assert act.actionable_id == "act-payment-gateway"
    assert act.risk_type == "REVENUE_RISK"
    assert act.severity == Severity.CRITICAL
    assert "cls-payment-gateway" in act.supporting_cluster_ids
    assert "iss-1" in act.supporting_issue_ids
    assert "evt-1" in act.supporting_event_ids
    assert act.priority_score == 45.0  # 40 (CRITICAL) + 5 (occurrence_count)
