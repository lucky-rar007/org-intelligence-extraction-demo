"""Generates executive-level actionable recommendations from high-risk active clusters."""

import logging
from typing import List
from domain.enums import IssueStatus, Severity
from domain.models import IssueCluster, FounderActionable

logger = logging.getLogger(__name__)


class ActionableGenerator:
    """Rolls up active operational clusters into business-level recommendations (FounderActionable)."""

    def generate_actionables(self, clusters: List[IssueCluster], report_date: str) -> List[FounderActionable]:
        """Analyze active issue clusters and generate founder actionables.

        Args:
            clusters: List of active and resolved IssueCluster objects.
            report_date: The date this report covers (YYYY-MM-DD).

        Returns:
            List of generated FounderActionable objects sorted by priority score descending.
        """
        actionables = []
        active_clusters = [c for c in clusters if c.status in (IssueStatus.OPEN, IssueStatus.MONITORING)]

        severity_weight = {
            Severity.CRITICAL: 40.0,
            Severity.HIGH: 30.0,
            Severity.MEDIUM: 20.0,
            Severity.LOW: 10.0,
        }

        for idx, cluster in enumerate(active_clusters, 1):
            actionable_id = f"act-{cluster.cluster_id.replace('cls-', '')}"
            
            # Formulate premium title and why-matters summary
            title = f"{cluster.title} Review"
            
            # Map risk descriptions
            if cluster.risk_type == "REVENUE_RISK":
                why_matters = f"Repeated payment processing and transaction anomalies are causing user checkout friction, directly threatening revenue."
            elif cluster.risk_type == "CUSTOMER_RISK":
                why_matters = f"Unresolved deployment delays and milestone slips are increasing delivery friction with key clients."
            elif cluster.risk_type == "QUALITY_RISK":
                why_matters = f"Mobile application instabilities and crash reports are degrading product quality and user experience."
            elif cluster.risk_type == "INFRASTRUCTURE_RISK":
                why_matters = f"System performance degradations and caching failures are threatening core application stability."
            elif cluster.risk_type == "DELIVERY_RISK":
                why_matters = f"Build and pipeline failures are stalling development velocity and delaying release milestones."
            else:
                why_matters = f"Operational incidents under '{cluster.title}' are affecting regular workflow velocity."

            # Priority score = severity weight + occurrence count
            weight = severity_weight.get(cluster.severity, 10.0)
            priority_score = weight + float(cluster.occurrence_count)

            actionable = FounderActionable(
                actionable_id=actionable_id,
                title=title,
                summary=why_matters,
                risk_type=cluster.risk_type,
                severity=cluster.severity,
                recommended_action=cluster.recommended_action,
                supporting_cluster_ids=[cluster.cluster_id],
                supporting_issue_ids=cluster.supporting_issue_ids,
                supporting_event_ids=cluster.supporting_event_ids,
                confidence_score=cluster.confidence_score,
                source_teams=cluster.source_teams,
                source_channels=cluster.source_channels,
                created_date=report_date,
                priority_score=priority_score
            )
            actionables.append(actionable)

        # Sort actionables by priority score descending
        actionables.sort(key=lambda a: a.priority_score, reverse=True)
        logger.info("Generated %d founder actionables.", len(actionables))
        return actionables
