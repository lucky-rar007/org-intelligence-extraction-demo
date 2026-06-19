"""Aggregates extracted events and observations into intelligence findings.

This module generates higher-level organizational intelligence by detecting
patterns across events, issues, and observations. The most valuable founder
insights often emerge from repeated observations rather than isolated events.

Intelligence findings are generated from:
A) Recurring issues and event patterns
B) Aggregated observations (weak signals that accumulate over time)

Phase 2: All findings receive founder classification (impact, attention, relevance).
Only OPEN/MONITORING issues contribute to findings (resolved issues are excluded).
"""

import logging
from collections import Counter
from datetime import datetime, timezone

from domain.enums import IntelligenceType, IssueStatus, ObservationType, Severity, FounderAttention
from domain.models import Event, IntelligenceFinding, Issue, Observation
from pipeline.founder_classifier import FounderClassifier
from utils.hashing import generate_id
import config

logger = logging.getLogger(__name__)


# Maps observation types to the intelligence findings they generate
_OBSERVATION_FINDING_MAP: dict[ObservationType, dict] = {
    ObservationType.KNOWLEDGE_GAP: {
        "title": "Documentation Debt Detected",
        "summary_template": "Repeated knowledge gap signals ({count} occurrences) suggest missing or outdated documentation causing recurring questions.",
        "recommendation": "Audit onboarding and internal documentation. Create FAQs for frequently asked operational questions.",
        "intelligence_type": IntelligenceType.OPERATIONAL_RISK,
    },
    ObservationType.DOCUMENTATION_GAP: {
        "title": "Documentation Gap Impacting Productivity",
        "summary_template": "Documentation gaps detected across {count} signals, indicating teams are repeatedly unable to find needed information.",
        "recommendation": "Prioritize documentation sprint. Identify top 5 most-asked questions and create permanent documentation.",
        "intelligence_type": IntelligenceType.OPERATIONAL_RISK,
    },
    ObservationType.OWNERSHIP_CONFUSION: {
        "title": "Responsibility Ambiguity Across Teams",
        "summary_template": "Ownership confusion detected in {count} observations, indicating unclear module/decision ownership affecting team velocity.",
        "recommendation": "Establish clear RACI matrix for key modules and decision-making areas. Communicate ownership publicly.",
        "intelligence_type": IntelligenceType.OPERATIONAL_RISK,
    },
    ObservationType.COORDINATION_FRICTION: {
        "title": "Coordination Bottleneck Detected",
        "summary_template": "{count} coordination friction signals detected, suggesting systemic alignment problems between teams.",
        "recommendation": "Review cross-team handoff processes. Consider introducing lightweight sync rituals or shared visibility tools.",
        "intelligence_type": IntelligenceType.DELIVERY_RISK,
    },
    ObservationType.DEPENDENCY_WAITING: {
        "title": "Dependency Bottleneck Impacting Delivery",
        "summary_template": "Repeated dependency waiting signals ({count} occurrences) indicate teams are frequently blocked waiting for other teams.",
        "recommendation": "Map critical dependency chains. Explore self-service tooling or dedicated support rotations for common blockers.",
        "intelligence_type": IntelligenceType.DELIVERY_RISK,
    },
    ObservationType.PROCESS_COMPLIANCE: {
        "title": "Process Discipline Concerns",
        "summary_template": "{count} process compliance observations detected, suggesting recurring issues with standup attendance, ticket hygiene, or workflow adherence.",
        "recommendation": "Review team process agreements. Automate compliance reminders where possible. Investigate root causes of non-compliance.",
        "intelligence_type": IntelligenceType.OPERATIONAL_RISK,
    },
    ObservationType.RESOURCE_CONTENTION: {
        "title": "Shared Resource Contention",
        "summary_template": "Resource contention detected across {count} signals, indicating teams competing for shared environments, tools, or personnel.",
        "recommendation": "Evaluate resource sharing policies. Consider dedicated environments or scheduling for high-contention resources.",
        "intelligence_type": IntelligenceType.OPERATIONAL_RISK,
    },
    ObservationType.COMMUNICATION_PATTERN: {
        "title": "Communication Pattern Anomaly",
        "summary_template": "{count} notable communication patterns detected, suggesting potential information silos or escalation chain issues.",
        "recommendation": "Audit information flow across teams. Ensure critical decisions and context are visible to all stakeholders.",
        "intelligence_type": IntelligenceType.OPERATIONAL_RISK,
    },
    ObservationType.OTHER: {
        "title": "General Operational Observations",
        "summary_template": "{count} miscellaneous operational signals detected, suggesting minor coordination friction or general updates.",
        "recommendation": "Monitor general signals for emerging trends or categories. Address underlying noise if occurrences rise.",
        "intelligence_type": IntelligenceType.OPERATIONAL_RISK,
    },
}


class Aggregator:
    """Generates intelligence findings from events, issues, and observations.

    Applies rule-based pattern detection to identify:
    - Recurring issues that signal systemic problems
    - Growing issues with escalating severity
    - Client pressure from elevated requests/escalations
    - Delivery risks from blockers and delays
    - Operational risks from infrastructure and environment issues
    - Observation-based insights from accumulated weak signals
    """

    def __init__(self) -> None:
        """Initialize the Aggregator."""
        self._aggregation_threshold = config.OBSERVATION_AGGREGATION_THRESHOLD
        self._classifier = FounderClassifier()

    def generate_findings(
        self,
        events: list[Event],
        issues: list[Issue],
        observations: list[Observation],
        report_date: str | None = None,
    ) -> list[IntelligenceFinding]:
        """Generate intelligence findings from events, issues, and observations.

        Args:
            events: Actionable events from the current run.
            issues: All tracked issues (including historical).
            observations: All observations (current + historical).
            report_date: The date being processed (YYYY-MM-DD format).

        Returns:
            A list of IntelligenceFinding domain objects.
        """
        findings: list[IntelligenceFinding] = []

        # Generate findings from issue patterns (only OPEN/MONITORING issues)
        issue_findings = self._generate_issue_findings(issues)
        findings.extend(issue_findings)

        # Generate findings from event patterns
        event_findings = self._generate_event_findings(events)
        findings.extend(event_findings)

        # Generate findings from observation aggregation
        observation_findings = self._generate_observation_findings(observations, report_date)
        findings.extend(observation_findings)

        # Generate positive findings for resolved issues
        if report_date:
            resolution_findings = self._generate_resolution_findings(issues, report_date)
            findings.extend(resolution_findings)

        # Deduplicate findings by title
        findings = self._deduplicate_findings(findings)

        # Apply founder classification to all findings
        for finding in findings:
            self._classifier.classify_finding(finding)

        logger.info(
            "Generated %d intelligence findings (%d from issues, %d from events, %d from observations)",
            len(findings), len(issue_findings), len(event_findings), len(observation_findings)
        )
        return findings

    def _generate_resolution_findings(
        self, issues: list[Issue], report_date: str
    ) -> list[IntelligenceFinding]:
        """Generate findings for issues resolved on the current report date."""
        findings: list[IntelligenceFinding] = []
        try:
            report_dt = datetime.fromisoformat(report_date).date()
        except ValueError:
            return findings

        for issue in issues:
            if issue.status == IssueStatus.RESOLVED and issue.resolved_at:
                if issue.resolved_at.date() == report_dt:
                    # Generate title based on issue name to show positive resolution
                    title = issue.title
                    title_lower = title.lower()
                    if "gateway" in title_lower or "incident" in title_lower:
                        finding_title = f"{title} Incident Resolved"
                    elif "risk" in title_lower or "deployment" in title_lower or "delivery" in title_lower:
                        finding_title = f"{title} Risk Mitigated"
                    elif "webhook" in title_lower or "stability" in title_lower or "connection" in title_lower:
                        finding_title = f"{title} Stability Restored"
                    else:
                        finding_title = f"{title} Resolved"

                    # Clean up double words like "Delay Delay" or "Resolved Resolved"
                    if "resolved resolved" in finding_title.lower():
                        finding_title = finding_title.replace("Resolved Resolved", "Resolved")

                    evidence_str = ""
                    if issue.resolution_summary:
                        evidence_str = f" Resolution details: {issue.resolution_summary}."

                    summary = (
                        f"The active issue '{issue.title}' has been successfully resolved. "
                        f"It was open for {issue.days_open} days and had occurred {issue.occurrence_count} times.{evidence_str}"
                    )

                    finding = IntelligenceFinding(
                        id=generate_id("fnd", "resolved", issue.id),
                        title=finding_title,
                        summary=summary,
                        severity=issue.severity,
                        supporting_event_ids=list(issue.resolution_evidence),
                        related_issue_ids=[issue.id],
                        recommendation="Monitor production metrics to ensure the resolution remains stable and no regressions occur.",
                        created_at=datetime.now(timezone.utc),
                        finding_type=IntelligenceType.OPERATIONAL_RISK,
                        confidence_score=1.0,
                        evidence_count=len(issue.resolution_evidence) or 1,
                    )

                    # Classify finding using the same founder impact as the issue
                    finding.founder_impact = issue.founder_impact
                    finding.founder_attention = FounderAttention.FYI
                    finding.relevance_level = issue.relevance_level

                    findings.append(finding)
                    logger.info("Generated resolution finding for issue '%s'", issue.title)

        return findings

    def _generate_issue_findings(self, issues: list[Issue]) -> list[IntelligenceFinding]:
        """Generate findings from issue recurrence and severity patterns.

        Only generates findings from OPEN or MONITORING issues.
        Resolved/Closed issues do not contribute to active findings.

        Args:
            issues: All tracked issues.

        Returns:
            Intelligence findings derived from issue patterns.
        """
        findings: list[IntelligenceFinding] = []

        for issue in issues:
            # Only generate findings for active issues
            if issue.status not in (IssueStatus.OPEN, IssueStatus.MONITORING):
                continue

            # Recurring issue: occurrence_count >= 3
            if issue.occurrence_count >= 3:
                finding = IntelligenceFinding(
                    id=generate_id("fnd", "recurring", issue.title),
                    title=f"Recurring Issue: {issue.title}",
                    summary=(
                        f"Issue '{issue.title}' has occurred {issue.occurrence_count} times "
                        f"since {issue.first_seen.date().isoformat()}. This recurring pattern "
                        f"suggests a systemic problem that requires structural remediation."
                    ),
                    severity=issue.severity,
                    supporting_event_ids=list(issue.linked_event_ids),
                    related_issue_ids=[issue.id],
                    recommendation=(
                        f"Investigate root cause of '{issue.title}'. "
                        f"Consider dedicated task force or architectural change to resolve permanently."
                    ),
                    created_at=datetime.now(timezone.utc),
                    finding_type=IntelligenceType.RECURRING_ISSUE,
                    confidence_score=min(0.5 + (issue.occurrence_count * 0.1), 1.0),
                    evidence_count=issue.occurrence_count,
                )
                findings.append(finding)

            # Growing issue: severity has escalated over time
            if len(issue.severity_history) >= 2:
                severity_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
                severities = [
                    severity_order.get(sh["severity"], 0)
                    for sh in issue.severity_history
                ]
                if severities[-1] > severities[0]:
                    finding = IntelligenceFinding(
                        id=generate_id("fnd", "growing", issue.title),
                        title=f"Growing Issue: {issue.title}",
                        summary=(
                            f"Issue '{issue.title}' has escalated in severity from "
                            f"{issue.severity_history[0]['severity']} to {issue.severity_history[-1]['severity']}. "
                            f"This growing trend indicates the problem is worsening."
                        ),
                        severity=Severity.HIGH,
                        supporting_event_ids=list(issue.linked_event_ids),
                        related_issue_ids=[issue.id],
                        recommendation=(
                            f"Escalate '{issue.title}' for immediate attention. "
                            f"The severity trajectory suggests this will become critical without intervention."
                        ),
                        created_at=datetime.now(timezone.utc),
                        finding_type=IntelligenceType.GROWING_ISSUE,
                        confidence_score=0.8,
                        evidence_count=len(issue.severity_history),
                    )
                    findings.append(finding)

        return findings

    def _generate_event_findings(self, events: list[Event]) -> list[IntelligenceFinding]:
        """Generate findings from patterns in the current batch of events.

        Args:
            events: Actionable events from the current run.

        Returns:
            Intelligence findings derived from event patterns.
        """
        findings: list[IntelligenceFinding] = []

        if not events:
            return findings

        # Count events by type
        type_counts: Counter[str] = Counter()
        type_events: dict[str, list[Event]] = {}
        for event in events:
            type_key = event.event_type.value
            type_counts[type_key] += 1
            type_events.setdefault(type_key, []).append(event)

        # Client pressure: multiple client-related events
        client_types = {"CLIENT_ESCALATION", "CLIENT_REQUEST"}
        client_count = sum(type_counts.get(ct, 0) for ct in client_types)
        if client_count >= 2:
            client_event_ids = []
            for ct in client_types:
                client_event_ids.extend([e.id for e in type_events.get(ct, [])])
            findings.append(IntelligenceFinding(
                id=generate_id("fnd", "client-pressure", str(client_count)),
                title="Elevated Client Pressure",
                summary=(
                    f"{client_count} client-related events detected in this period, "
                    f"indicating elevated client pressure that may affect team focus and delivery."
                ),
                severity=Severity.HIGH,
                supporting_event_ids=client_event_ids,
                recommendation=(
                    "Review client communication channels. Ensure dedicated client-facing resources. "
                    "Consider proactive client updates to reduce escalation frequency."
                ),
                created_at=datetime.now(timezone.utc),
                finding_type=IntelligenceType.CLIENT_PRESSURE,
                confidence_score=min(0.6 + (client_count * 0.1), 1.0),
                evidence_count=client_count,
            ))

        # Delivery risk: multiple delivery-blocking events
        delivery_types = {"DELIVERY_BLOCKED", "RELEASE_DELAY", "DEPENDENCY_WAIT"}
        delivery_count = sum(type_counts.get(dt, 0) for dt in delivery_types)
        if delivery_count >= 2:
            delivery_event_ids = []
            for dt in delivery_types:
                delivery_event_ids.extend([e.id for e in type_events.get(dt, [])])
            findings.append(IntelligenceFinding(
                id=generate_id("fnd", "delivery-risk", str(delivery_count)),
                title="Delivery Predictability Risk",
                summary=(
                    f"{delivery_count} delivery-impacting events detected, "
                    f"suggesting systemic delivery risks that may affect timelines."
                ),
                severity=Severity.HIGH,
                supporting_event_ids=delivery_event_ids,
                recommendation=(
                    "Review delivery pipeline for bottlenecks. Identify and remove systemic blockers. "
                    "Consider buffer time in sprint planning."
                ),
                created_at=datetime.now(timezone.utc),
                finding_type=IntelligenceType.DELIVERY_RISK,
                confidence_score=min(0.6 + (delivery_count * 0.1), 1.0),
                evidence_count=delivery_count,
            ))

        # Operational risk: infrastructure/environment issues
        ops_types = {"INFRASTRUCTURE_ISSUE", "ENVIRONMENT_ISSUE", "PRODUCTION_INCIDENT"}
        ops_count = sum(type_counts.get(ot, 0) for ot in ops_types)
        if ops_count >= 2:
            ops_event_ids = []
            for ot in ops_types:
                ops_event_ids.extend([e.id for e in type_events.get(ot, [])])
            findings.append(IntelligenceFinding(
                id=generate_id("fnd", "operational-risk", str(ops_count)),
                title="Infrastructure Instability",
                summary=(
                    f"{ops_count} infrastructure/environment events detected, "
                    f"indicating potential instability in the operational environment."
                ),
                severity=Severity.HIGH,
                supporting_event_ids=ops_event_ids,
                recommendation=(
                    "Audit infrastructure health. Review monitoring and alerting coverage. "
                    "Prioritize stability improvements over feature work if pattern continues."
                ),
                created_at=datetime.now(timezone.utc),
                finding_type=IntelligenceType.OPERATIONAL_RISK,
                confidence_score=min(0.6 + (ops_count * 0.1), 1.0),
                evidence_count=ops_count,
            ))

        # Critical incident: any CRITICAL severity event generates an immediate finding
        critical_events = [e for e in events if e.severity == Severity.CRITICAL]
        for critical_event in critical_events:
            findings.append(IntelligenceFinding(
                id=generate_id("fnd", "critical", critical_event.id),
                title=f"Critical Incident: {critical_event.title}",
                summary=(
                    f"Critical severity event detected: {critical_event.description}. "
                    f"This requires immediate executive attention."
                ),
                severity=Severity.CRITICAL,
                supporting_event_ids=[critical_event.id],
                recommendation=(
                    f"Immediate action required for '{critical_event.title}'. "
                    f"Verify incident response is activated and stakeholders are informed."
                ),
                created_at=datetime.now(timezone.utc),
                finding_type=IntelligenceType.CRITICAL_INCIDENT,
                confidence_score=critical_event.confidence_score,
                evidence_count=1,
            ))

        return findings

    def _generate_observation_findings(
        self, observations: list[Observation], report_date: str | None = None
    ) -> list[IntelligenceFinding]:
        """Generate findings from aggregated observation patterns.

        Groups observations by type and generates findings when the count
        exceeds the aggregation threshold.

        Args:
            observations: All observations (current + historical).
            report_date: The report date (YYYY-MM-DD format).

        Returns:
            Intelligence findings derived from observation patterns.
        """
        findings: list[IntelligenceFinding] = []

        if not observations:
            return findings

        # Filter observations to rolling 7 days if report_date is available
        report_dt = None
        if report_date:
            try:
                report_dt = datetime.strptime(report_date, "%Y-%m-%d").date()
            except ValueError:
                pass

        filtered_observations = []
        for obs in observations:
            if report_dt:
                days_diff = (report_dt - obs.last_seen.date()).days
                if 0 <= days_diff <= 7:
                    filtered_observations.append(obs)
            else:
                filtered_observations.append(obs)

        # Group observations by type
        obs_by_type: dict[ObservationType, list[Observation]] = {}
        for obs in filtered_observations:
            obs_by_type.setdefault(obs.observation_type, []).append(obs)

        # Generate findings for each type exceeding the threshold
        for obs_type, obs_list in obs_by_type.items():
            count = len(obs_list)
            if count < self._aggregation_threshold:
                continue

            mapping = _OBSERVATION_FINDING_MAP.get(obs_type)
            if mapping is None:
                # Generate a generic finding for unmapped types
                finding = IntelligenceFinding(
                    id=generate_id("fnd", "obs-pattern", obs_type.value),
                    title=f"Observation Pattern: {obs_type.value.replace('_', ' ').title()}",
                    summary=(
                        f"{count} '{obs_type.value}' observations detected. "
                        f"This pattern may indicate an emerging organizational concern."
                    ),
                    severity=Severity.MEDIUM,
                    related_observation_ids=[o.id for o in obs_list],
                    recommendation="Investigate the root cause of this recurring observation pattern.",
                    created_at=datetime.now(timezone.utc),
                    finding_type=IntelligenceType.OPERATIONAL_RISK,
                    confidence_score=min(0.4 + (count * 0.1), 0.9),
                    evidence_count=count,
                )
            else:
                severity = Severity.MEDIUM
                if count >= 10:
                    severity = Severity.CRITICAL
                elif count >= 5:
                    severity = Severity.HIGH

                finding = IntelligenceFinding(
                    id=generate_id("fnd", "obs-pattern", obs_type.value),
                    title=mapping["title"],
                    summary=mapping["summary_template"].format(count=count),
                    severity=severity,
                    related_observation_ids=[o.id for o in obs_list],
                    recommendation=mapping["recommendation"],
                    created_at=datetime.now(timezone.utc),
                    finding_type=mapping["intelligence_type"],
                    confidence_score=min(0.5 + (count * 0.1), 0.95),
                    evidence_count=count,
                )

            findings.append(finding)
            logger.debug(
                "Generated observation finding: '%s' (type=%s, count=%d)",
                finding.title, obs_type.value, count
            )

        return findings

    def _deduplicate_findings(
        self, findings: list[IntelligenceFinding]
    ) -> list[IntelligenceFinding]:
        """Remove duplicate findings based on their deterministic IDs.

        Args:
            findings: Raw list of findings that may contain duplicates.

        Returns:
            Deduplicated list of findings.
        """
        seen_ids: set[str] = set()
        unique_findings: list[IntelligenceFinding] = []

        for finding in findings:
            if finding.id not in seen_ids:
                seen_ids.add(finding.id)
                unique_findings.append(finding)

        if len(unique_findings) < len(findings):
            logger.debug(
                "Deduplicated findings: %d → %d",
                len(findings), len(unique_findings)
            )

        return unique_findings
