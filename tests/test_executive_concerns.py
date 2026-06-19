import datetime
from domain.enums import IssueStatus, Severity
from domain.models import IssueCluster, ExecutiveConcern
from pipeline.concern_generator import ConcernGenerator


def test_executive_concerns_synthesis():
    """Verify that operational clusters roll up into correct executive concerns."""
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # 1. Revenue cluster
    cluster_rev = IssueCluster(
        cluster_id="cls-payment-gateway",
        title="Payment Gateway Rollout Problems",
        summary="Payment failure in gateway.",
        business_area="Finance / Checkout",
        severity=Severity.HIGH,
        status=IssueStatus.OPEN,
        days_open=2,
        first_seen=now,
        last_seen=now,
        occurrence_count=3,
        supporting_issue_ids=["iss-1"],
        supporting_event_ids=["evt-1"],
        recommended_action="Review gateway release process.",
        owner_candidates=["Aditya"],
        trend="NEW",
        risk_type="REVENUE_RISK",
        source_channels=["engineering"],
        source_teams=["Core Eng"],
        confidence_score=0.9,
        timeline=[]
    )

    # 2. Delivery cluster (Client ABC)
    cluster_del = IssueCluster(
        cluster_id="cls-client-abc",
        title="Client ABC Deployment Issues",
        summary="Release delay for Client ABC.",
        business_area="Client Relations / Delivery",
        severity=Severity.MEDIUM,
        status=IssueStatus.OPEN,
        days_open=4,
        first_seen=now,
        last_seen=now,
        occurrence_count=5,
        supporting_issue_ids=["iss-2"],
        supporting_event_ids=["evt-2"],
        recommended_action="Rebalance ABC team resources.",
        owner_candidates=["Ananya"],
        trend="STABLE",
        risk_type="CUSTOMER_RISK",
        source_channels=["engineering"],
        source_teams=["Core Eng"],
        confidence_score=0.9,
        timeline=[]
    )

    # 3. Knowledge/Infrastructure cluster (Redis)
    cluster_know = IssueCluster(
        cluster_id="cls-redis-cache",
        title="Redis Infrastructure Issues",
        summary="Redis memory limit hit.",
        business_area="Infrastructure / Caching",
        severity=Severity.CRITICAL,
        status=IssueStatus.OPEN,
        days_open=1,
        first_seen=now,
        last_seen=now,
        occurrence_count=2,
        supporting_issue_ids=["iss-3"],
        supporting_event_ids=["evt-3"],
        recommended_action="Mitigate Redis SPOF.",
        owner_candidates=["Siddharth"],
        trend="WORSENING",
        risk_type="INFRASTRUCTURE_RISK",
        source_channels=["engineering"],
        source_teams=["Core Eng"],
        confidence_score=0.9,
        timeline=[]
    )

    generator = ConcernGenerator()
    concerns = generator.generate_concerns([cluster_rev, cluster_del, cluster_know])

    # 3 Concerns should be created
    assert len(concerns) == 3

    # Sorted by severity (CRITICAL first): Redis is CRITICAL, so Knowledge Concentration Risk should be first!
    assert concerns[0].title == "Knowledge Concentration Risk"
    assert concerns[0].severity == Severity.CRITICAL
    assert "Redis Infrastructure Issues" in concerns[0].supporting_clusters
    assert "cls-redis-cache" in concerns[0].supporting_cluster_ids

    # Revenue reliability should be present
    rev_concern = next(con for con in concerns if con.title == "Revenue Reliability Risk")
    assert rev_concern.severity == Severity.HIGH
    assert "Payment Gateway Rollout Problems" in rev_concern.supporting_clusters

    # Delivery execution should be present
    del_concern = next(con for con in concerns if con.title == "Delivery Execution Risk")
    assert del_concern.severity == Severity.MEDIUM
    assert "Client ABC Deployment Issues" in del_concern.supporting_clusters
