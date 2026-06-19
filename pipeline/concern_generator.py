"""Synthesizes operational clusters into high-level executive concerns for founder review."""

import logging
from typing import List, Dict, Any

from domain.enums import IssueStatus, Severity
from domain.models import IssueCluster, ExecutiveConcern

logger = logging.getLogger(__name__)


class ConcernGenerator:
    """Groups active operational clusters into broad business-level concerns (ExecutiveConcern)."""

    def generate_concerns(self, clusters: List[IssueCluster]) -> List[ExecutiveConcern]:
        """Group active clusters into executive concerns.

        Args:
            clusters: List of active and resolved IssueCluster objects.

        Returns:
            List of generated ExecutiveConcern objects.
        """
        active_clusters = [c for c in clusters if c.status in (IssueStatus.OPEN, IssueStatus.MONITORING)]
        if not active_clusters:
            return []

        # Categories for concerns
        revenue_clusters = []
        delivery_clusters = []
        knowledge_clusters = []

        for c in active_clusters:
            title_lower = c.title.lower()
            summary_lower = c.summary.lower()
            risk = c.risk_type

            # 1. Revenue Reliability Risk
            if (risk == "REVENUE_RISK" or 
                any(kw in title_lower or kw in summary_lower for kw in ["payment", "checkout", "webhook", "charge", "paytm"])):
                revenue_clusters.append(c)

            # 2. Knowledge Concentration Risk (Tech silos, Redis, Mobile concentration)
            elif (risk == "INFRASTRUCTURE_RISK" or 
                  any(kw in title_lower or kw in summary_lower for kw in ["redis", "database", "db", "silo", "spof", "bottleneck"])):
                knowledge_clusters.append(c)

            # 3. Delivery Execution Risk (default fallback for clients and release tasks)
            else:
                delivery_clusters.append(c)

        concerns = []
        severity_order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]

        # Helper to compute severity
        def get_max_severity(child_clusters: List[IssueCluster]) -> Severity:
            highest = Severity.LOW
            for cc in child_clusters:
                if severity_order.index(cc.severity) > severity_order.index(highest):
                    highest = cc.severity
            return highest

        # Synthesis Rule 1: Revenue Reliability Risk
        if revenue_clusters:
            concerns.append(ExecutiveConcern(
                concern_id="con-revenue-reliability",
                title="Revenue Reliability Risk",
                risk_type="REVENUE_RISK",
                supporting_clusters=[c.title for c in revenue_clusters],
                severity=get_max_severity(revenue_clusters),
                recommendation="Review payment infrastructure ownership and reliability roadmap.",
                supporting_cluster_ids=[c.cluster_id for c in revenue_clusters]
            ))

        # Synthesis Rule 2: Delivery Execution Risk
        if delivery_clusters:
            concerns.append(ExecutiveConcern(
                concern_id="con-delivery-execution",
                title="Delivery Execution Risk",
                risk_type="CUSTOMER_RISK",
                supporting_clusters=[c.title for c in delivery_clusters],
                severity=get_max_severity(delivery_clusters),
                recommendation="Rebalance client delivery resources and tighten milestone checks.",
                supporting_cluster_ids=[c.cluster_id for c in delivery_clusters]
            ))

        # Synthesis Rule 3: Knowledge Concentration Risk
        if knowledge_clusters:
            concerns.append(ExecutiveConcern(
                concern_id="con-knowledge-concentration",
                title="Knowledge Concentration Risk",
                risk_type="TEAM_RISK",
                supporting_clusters=[c.title for c in knowledge_clusters],
                severity=get_max_severity(knowledge_clusters),
                recommendation="Schedule secondary owner knowledge transfers and review technical concentration silos.",
                supporting_cluster_ids=[c.cluster_id for c in knowledge_clusters]
            ))

        # Sort concerns by severity order descending
        concerns.sort(key=lambda con: severity_order.index(con.severity), reverse=True)
        logger.info("Synthesized %d executive concerns.", len(concerns))
        return concerns
