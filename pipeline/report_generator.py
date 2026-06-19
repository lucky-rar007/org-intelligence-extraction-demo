"""Generates executive reports and logs from aggregated data.

This module produces structured JSON reports designed to power a
founder/executive dashboard. Output is always structured JSON — never
markdown or plain text.

The report includes:
- Executive summary (LLM-generated with template fallback)
- Critical actionables sorted by attention > severity > recurrence
- Open issues (FOUNDER-relevant only in primary view)
- Monitoring issues
- Recently resolved issues
- Intelligence findings from events and observations
- Quantitative pipeline metrics including founder relevance breakdown
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Any

from domain.enums import (
    FounderAttention, FounderImpact, IssueStatus, RelevanceLevel, Severity,
)
from domain.models import (
    Event,
    FounderReport,
    IntelligenceFinding,
    Issue,
    Observation,
)
from llm.llm_client import LLMClient
from llm.prompt_loader import PromptLoader
from utils.date_utils import days_between, parse_filename_date
import config

logger = logging.getLogger(__name__)


# Severity sort order: CRITICAL first
_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}

# Attention sort order: IMMEDIATE_ACTION first
_ATTENTION_ORDER = {
    FounderAttention.IMMEDIATE_ACTION: 0,
    FounderAttention.ACTION_REQUIRED: 1,
    FounderAttention.MONITOR: 2,
    FounderAttention.FYI: 3,
}


class ReportGenerator:
    """Generates structured JSON founder reports from aggregated pipeline data."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        prompt_loader: Optional[PromptLoader] = None,
    ) -> None:
        """Initialize the ReportGenerator.

        Args:
            llm_client: Optional LLM client for executive summary generation.
                        If None, a template-based fallback is used.
            prompt_loader: Optional prompt loader for LLM prompts.
        """
        self.llm_client = llm_client
        self.prompt_loader = prompt_loader or PromptLoader()

    def generate_report(
        self,
        report_date: str,
        events: list[Event],
        observations: list[Observation],
        issues: list[Issue],
        findings: list[IntelligenceFinding],
        threads_processed: int,
        people_risks: list[dict[str, Any]] | None = None,
        knowledge_risks: list[dict[str, Any]] | None = None,
        commitment_risks: list[dict[str, Any]] | None = None,
        team_health_signals: list[dict[str, Any]] | None = None,
        top_bottlenecks: list[str] | None = None,
        top_dependency_nodes: list[str] | None = None,
        commitments_due: list[dict[str, Any]] | None = None,
        overdue_commitments: list[dict[str, Any]] | None = None,
        knowledge_concentration: list[dict[str, Any]] | None = None,
        issue_clusters: list[dict[str, Any]] | None = None,
        founder_actionables: list[dict[str, Any]] | None = None,
        high_risk_clusters: list[dict[str, Any]] | None = None,
        executive_concerns: list[dict[str, Any]] | None = None,
    ) -> FounderReport:
        """Generate a complete founder-facing report.

        Args:
            report_date: The date covered by this report (YYYY-MM-DD).
            events: Actionable events from this run.
            observations: Observations from this run.
            issues: All tracked issues (including historical).
            findings: Intelligence findings from aggregation.
            threads_processed: Number of conversation threads processed.

        Returns:
            A FounderReport domain object ready for JSON serialization.
        """
        now = datetime.now(timezone.utc)

        # Build report sections
        executive_summary = self._build_executive_summary(
            report_date, events, observations, issues, findings
        )
        critical_actionables = self._build_critical_actionables(events, issues, report_date)
        open_issues = self._build_open_issues(issues, report_date)
        monitoring_issues = self._build_monitoring_issues(issues, report_date)
        recently_resolved = self._build_recently_resolved(issues, report_date)
        intelligence_findings = self._build_intelligence_findings(findings)
        metrics = self._build_metrics(
            threads_processed, events, observations, issues, report_date
        )

        # Step 9 Dashboard Section Computations
        worsening_clusters = [c for c in (issue_clusters or []) if c.get("trend") == "WORSENING"]
        new_clusters = [c for c in (issue_clusters or []) if c.get("trend") == "NEW"]
        long_running_clusters = [c for c in (issue_clusters or []) if c.get("days_open", 0) > 5]
        delivery_risks = [c for c in (issue_clusters or []) if c.get("risk_type") == "DELIVERY_RISK"]
        revenue_risks = [c for c in (issue_clusters or []) if c.get("risk_type") == "REVENUE_RISK"]

        report = FounderReport(
            report_date=report_date,
            generated_at=now.isoformat(),
            executive_summary=executive_summary,
            executive_concerns=executive_concerns or [],
            founder_actionables=founder_actionables or [],
            high_risk_clusters=high_risk_clusters or [],
            worsening_clusters=worsening_clusters,
            new_clusters=new_clusters,
            long_running_clusters=long_running_clusters,
            delivery_risks=delivery_risks,
            revenue_risks=revenue_risks,
            critical_actionables=critical_actionables,
            open_issues=open_issues,
            monitoring_issues=monitoring_issues,
            recently_resolved=recently_resolved,
            intelligence_findings=intelligence_findings,
            people_risks=people_risks or [],
            knowledge_risks=knowledge_risks or [],
            commitment_risks=commitment_risks or [],
            team_health_signals=team_health_signals or [],
            top_bottlenecks=top_bottlenecks or [],
            top_dependency_nodes=top_dependency_nodes or [],
            commitments_due=commitments_due or [],
            overdue_commitments=overdue_commitments or [],
            knowledge_concentration=knowledge_concentration or [],
            issue_clusters=issue_clusters or [],
            metrics=metrics,
        )

        logger.info("Generated founder report for %s", report_date)
        return report

    def _build_executive_summary(
        self,
        report_date: str,
        events: list[Event],
        observations: list[Observation],
        issues: list[Issue],
        findings: list[IntelligenceFinding],
    ) -> dict:
        """Build the executive summary section.

        Attempts LLM-generated summary first, falls back to template-based.

        Args:
            report_date: The report date.
            events: Actionable events.
            observations: Observations.
            issues: All tracked issues.
            findings: Intelligence findings.

        Returns:
            A dictionary containing the executive summary.
        """
        # Count metrics for the summary
        critical_count = sum(1 for e in events if e.severity == Severity.CRITICAL)
        high_count = sum(1 for e in events if e.severity == Severity.HIGH)
        open_issues = [i for i in issues if i.status == IssueStatus.OPEN]
        monitoring = [i for i in issues if i.status == IssueStatus.MONITORING]
        resolved = [i for i in issues if i.status == IssueStatus.RESOLVED]

        # Founder relevance counts
        founder_issues = [
            i for i in issues
            if i.status in (IssueStatus.OPEN, IssueStatus.MONITORING)
            and i.relevance_level == RelevanceLevel.FOUNDER
        ]
        immediate_action = [
            i for i in issues
            if i.status in (IssueStatus.OPEN, IssueStatus.MONITORING)
            and i.founder_attention == FounderAttention.IMMEDIATE_ACTION
        ]

        # Try LLM-generated summary
        llm_summary = None
        if self.llm_client is not None:
            llm_summary = self._generate_llm_summary(
                report_date, events, observations, issues, findings
            )

        if llm_summary:
            summary_text = llm_summary
        else:
            # Template-based fallback
            summary_parts = [
                f"Organizational intelligence report for {report_date}.",
                f"Processed {len(events)} actionable events and {len(observations)} observations.",
            ]
            if critical_count > 0:
                summary_parts.append(f"{critical_count} critical events require immediate attention.")
            if high_count > 0:
                summary_parts.append(f"{high_count} high-severity events detected.")
            if founder_issues:
                summary_parts.append(f"{len(founder_issues)} founder-relevant issues identified.")
            if immediate_action:
                summary_parts.append(f"{len(immediate_action)} issues require immediate action.")
            if open_issues:
                summary_parts.append(f"{len(open_issues)} issues remain open.")
            if monitoring:
                summary_parts.append(f"{len(monitoring)} issues are being monitored.")
            if resolved:
                summary_parts.append(f"{len(resolved)} issues have been resolved.")
            if findings:
                summary_parts.append(f"{len(findings)} intelligence findings generated.")

            summary_text = " ".join(summary_parts)

        return {
            "narrative": summary_text,
            "critical_events": critical_count,
            "high_severity_events": high_count,
            "open_issues": len(open_issues),
            "monitoring_issues": len(monitoring),
            "resolved_issues": len(resolved),
            "founder_relevant_issues": len(founder_issues),
            "immediate_action_items": len(immediate_action),
            "total_findings": len(findings),
            "total_observations": len(observations),
        }

    def _generate_llm_summary(
        self,
        report_date: str,
        events: list[Event],
        observations: list[Observation],
        issues: list[Issue],
        findings: list[IntelligenceFinding],
    ) -> str | None:
        """Attempt to generate an executive summary using the LLM.

        Args:
            report_date: The report date.
            events: Actionable events.
            observations: Observations.
            issues: All tracked issues.
            findings: Intelligence findings.

        Returns:
            The generated summary text, or None if LLM generation fails.
        """
        try:
            # Build context for the prompt — focus on founder-relevant items
            founder_events = [
                e for e in events
                if e.relevance_level in (RelevanceLevel.FOUNDER, RelevanceLevel.LEADERSHIP)
            ]
            event_summaries = "\n".join(
                f"- [{e.severity.value}] [{e.founder_attention.value}] {e.title}: {e.description[:100]}"
                for e in founder_events[:15]
            )
            finding_summaries = "\n".join(
                f"- {f.title}: {f.summary[:100]}"
                for f in findings[:10]
            )

            # Only show open/monitoring issues
            active_issues = [
                i for i in issues
                if i.status in (IssueStatus.OPEN, IssueStatus.MONITORING)
            ]
            open_issue_summaries = "\n".join(
                f"- [{i.founder_attention.value}] {i.title} "
                f"(open {i.occurrence_count} times, severity: {i.severity.value}, "
                f"impact: {i.founder_impact.value})"
                for i in active_issues
                if i.relevance_level in (RelevanceLevel.FOUNDER, RelevanceLevel.LEADERSHIP)
            )
            observation_summary = f"{len(observations)} weak signals detected"

            prompt = self.prompt_loader.render_prompt(
                prompt_name="executive_summary",
                variables={
                    "report_date": report_date,
                    "events": event_summaries or "No actionable events.",
                    "findings": finding_summaries or "No findings.",
                    "open_issues": open_issue_summaries or "No open issues.",
                    "observations": observation_summary,
                }
            )

            response = self.llm_client.generate(prompt)
            return response.strip()

        except Exception as e:
            logger.warning("LLM summary generation failed, using template fallback: %s", str(e))
            return None

    def _build_critical_actionables(
        self, events: list[Event], issues: list[Issue], report_date: str
    ) -> list[dict]:
        """Build the critical actionables section.

        Sorted by: attention → severity → recurrence.
        Only FOUNDER-relevant items appear here.

        Each actionable includes full founder intelligence metadata.

        Args:
            events: Actionable events.
            issues: All tracked issues.
            report_date: The current report date.

        Returns:
            A list of actionable item dictionaries.
        """
        actionables = []

        # Build actionables from FOUNDER-relevant issues (OPEN or MONITORING)
        founder_issues = [
            i for i in issues
            if i.status in (IssueStatus.OPEN, IssueStatus.MONITORING)
            and i.relevance_level == RelevanceLevel.FOUNDER
        ]

        for issue in founder_issues:
            try:
                report_dt = datetime.fromisoformat(report_date).date()
            except ValueError:
                report_dt = issue.last_seen.date()

            days_open = days_between(issue.first_seen.date(), report_dt)

            # Derive recommended action based on founder impact type
            impact_actions = {
                FounderImpact.REVENUE_RISK: "Audit checkout funnel, payment gateway API response logs, and verify transaction failure rates.",
                FounderImpact.CUSTOMER_RISK: "Escalate customer relationship review, align account management, and verify support SLA compliance.",
                FounderImpact.DELIVERY_RISK: "Review sprint board bottlenecks, reallocate engineering resources, and address blocking dependencies.",
                FounderImpact.OPERATIONAL_RISK: "Audit infrastructure alarms, tune database connection pools, and review scaling policies.",
                FounderImpact.TEAM_RISK: "Conduct team health check-in, review workload distribution, and evaluate burnout mitigation steps.",
                FounderImpact.HIRING_RISK: "Accelerate recruitment pipeline, check open requisition statuses, and evaluate candidate sourcing strategies.",
                FounderImpact.STRATEGIC_RISK: "Align product roadmap milestones, review competitor market positions, and schedule executive strategic review.",
                FounderImpact.COMPLIANCE_RISK: "Review compliance audit requirements, address data security vulnerabilities, and verify GDPR/regulatory compliance.",
                FounderImpact.PRODUCT_RISK: "Analyze crash logs, inspect UI/UX regression patterns, and coordinate mobile app store release hotfixes.",
                FounderImpact.UNKNOWN: f"Conduct root-cause analysis for {issue.title} and assign clear ownership."
            }
            rec_action = impact_actions.get(issue.founder_impact, f"Conduct root-cause analysis for {issue.title} and assign clear ownership.")

            actionables.append({
                "title": issue.title,
                "summary": issue.summary,
                "severity": issue.severity.value,
                "founder_impact": issue.founder_impact.value,
                "founder_attention": issue.founder_attention.value,
                "days_open": days_open,
                "occurrence_count": issue.occurrence_count,
                "source_team": issue.affected_team or "Unknown",
                "source_channel": issue.affected_channel or "Unknown",
                "date": issue.first_seen.date().isoformat(),
                "recommended_action": rec_action,
                "status": issue.status.value,
            })

        # Sort: attention → severity → recurrence (descending)
        actionables.sort(
            key=lambda a: (
                _ATTENTION_ORDER.get(FounderAttention(a["founder_attention"]), 99),
                _SEVERITY_ORDER.get(Severity(a["severity"]), 99),
                -a["occurrence_count"],
            )
        )

        return actionables[:config.MAX_CRITICAL_ISSUES]

    def _build_open_issues(self, issues: list[Issue], report_date: str) -> list[dict]:
        """Build the open issues section with duration tracking.

        Only includes OPEN issues (not MONITORING or RESOLVED).

        Args:
            issues: All tracked issues.
            report_date: The current report date for days_open calculation.

        Returns:
            A list of open issue dictionaries.
        """
        open_issues = [
            i for i in issues
            if i.status == IssueStatus.OPEN
            and i.relevance_level in (RelevanceLevel.FOUNDER, RelevanceLevel.LEADERSHIP)
        ]

        # Sort by attention → severity (CRITICAL first)
        open_issues.sort(
            key=lambda i: (
                _ATTENTION_ORDER.get(i.founder_attention, 99),
                _SEVERITY_ORDER.get(i.severity, 99),
            )
        )

        result = []
        for issue in open_issues[:30]:
            try:
                report_dt = datetime.fromisoformat(report_date).date()
            except ValueError:
                report_dt = issue.last_seen.date()

            days_open = days_between(issue.first_seen.date(), report_dt)

            result.append({
                "title": issue.title,
                "status": issue.status.value,
                "days_open": days_open,
                "occurrence_count": issue.occurrence_count,
                "severity": issue.severity.value,
                "affected_team": issue.affected_team or "Unknown",
                "founder_impact": issue.founder_impact.value,
                "founder_attention": issue.founder_attention.value,
                "relevance_level": issue.relevance_level.value,
            })

        return result

    def _build_monitoring_issues(self, issues: list[Issue], report_date: str) -> list[dict]:
        """Build the monitoring issues section.

        Issues where a fix has been applied and is being validated.

        Args:
            issues: All tracked issues.
            report_date: The current report date.

        Returns:
            A list of monitoring issue dictionaries.
        """
        monitoring = [
            i for i in issues
            if i.status == IssueStatus.MONITORING
        ]

        result = []
        for issue in monitoring:
            try:
                report_dt = datetime.fromisoformat(report_date).date()
            except ValueError:
                report_dt = issue.last_seen.date()

            days_open = days_between(issue.first_seen.date(), report_dt)

            result.append({
                "title": issue.title,
                "status": issue.status.value,
                "days_open": days_open,
                "severity": issue.severity.value,
                "affected_team": issue.affected_team or "Unknown",
                "founder_impact": issue.founder_impact.value,
            })

        return result

    def _build_recently_resolved(self, issues: list[Issue], report_date: str) -> list[dict]:
        """Build the recently resolved section.

        Shows issues that have been resolved during the current reporting period.

        Args:
            issues: All tracked issues.
            report_date: The current report date.

        Returns:
            A list of resolved issue dictionaries.
        """
        try:
            report_dt = datetime.fromisoformat(report_date).date()
        except ValueError:
            report_dt = None

        resolved = []
        for i in issues:
            if i.status == IssueStatus.RESOLVED and i.resolved_at:
                if report_dt is None:
                    resolved.append(i)
                else:
                    days_diff = (report_dt - i.resolved_at.date()).days
                    if 0 <= days_diff < 7:
                        resolved.append(i)

        result = []
        for issue in resolved:
            result.append({
                "title": issue.title,
                "status": issue.status.value,
                "severity": issue.severity.value,
                "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
                "resolution_summary": issue.resolution_summary or "Automatically resolved",
                "affected_team": issue.affected_team or "Unknown",
                "founder_impact": issue.founder_impact.value,
            })

        return result

    def _build_intelligence_findings(
        self, findings: list[IntelligenceFinding]
    ) -> list[dict]:
        """Build the intelligence findings section.

        Args:
            findings: Intelligence findings from aggregation.

        Returns:
            A list of finding dictionaries.
        """
        # Sort findings by attention → severity
        sorted_findings = sorted(
            findings,
            key=lambda f: (
                _ATTENTION_ORDER.get(f.founder_attention, 99),
                _SEVERITY_ORDER.get(f.severity, 99),
            )
        )

        result = []
        for finding in sorted_findings[:config.MAX_EXECUTIVE_FINDINGS]:
            result.append({
                "title": finding.title,
                "summary": finding.summary,
                "recommendation": finding.recommendation,
                "confidence_score": round(finding.confidence_score, 2),
                "evidence_count": finding.evidence_count,
                "founder_impact": finding.founder_impact.value,
                "founder_attention": finding.founder_attention.value,
                "relevance_level": finding.relevance_level.value,
            })

        return result

    def _build_metrics(
        self,
        threads_processed: int,
        events: list[Event],
        observations: list[Observation],
        issues: list[Issue],
        report_date: str,
    ) -> dict[str, int]:
        """Build the quantitative metrics section with founder relevance breakdown.

        Args:
            threads_processed: Number of conversation threads processed.
            events: Actionable events.
            observations: Observations.
            issues: All tracked issues.
            report_date: The current report date.

        Returns:
            A dictionary of pipeline metrics.
        """
        open_issues = [i for i in issues if i.status == IssueStatus.OPEN]
        monitoring_issues = [i for i in issues if i.status == IssueStatus.MONITORING]
        resolved_issues = [i for i in issues if i.status == IssueStatus.RESOLVED]
        closed_issues = [i for i in issues if i.status == IssueStatus.CLOSED]

        # Founder relevance breakdown
        founder_relevant = [
            i for i in issues
            if i.status in (IssueStatus.OPEN, IssueStatus.MONITORING)
            and i.relevance_level == RelevanceLevel.FOUNDER
        ]
        leadership_relevant = [
            i for i in issues
            if i.status in (IssueStatus.OPEN, IssueStatus.MONITORING)
            and i.relevance_level == RelevanceLevel.LEADERSHIP
        ]
        team_relevant = [
            i for i in issues
            if i.status in (IssueStatus.OPEN, IssueStatus.MONITORING)
            and i.relevance_level == RelevanceLevel.TEAM
        ]

        critical_issues = [i for i in issues if i.severity == Severity.CRITICAL]
        high_severity = sum(
            1 for e in events
            if e.severity in (Severity.HIGH, Severity.CRITICAL)
        )

        # Calculate daily and weekly resolved metrics
        try:
            report_dt = datetime.fromisoformat(report_date).date()
        except ValueError:
            report_dt = datetime.now(timezone.utc).date()

        resolved_today = 0
        resolved_this_week = 0

        for issue in issues:
            if issue.status == IssueStatus.RESOLVED and issue.resolved_at:
                issue_resolved_dt = issue.resolved_at.date()
                if issue_resolved_dt == report_dt:
                    resolved_today += 1
                
                # Rolling 7 days: today and previous 6 days
                days_diff = (report_dt - issue_resolved_dt).days
                if 0 <= days_diff < 7:
                    resolved_this_week += 1

        return {
            "threads_processed": threads_processed,
            "events_extracted": len(events),
            "actionable_events": len(events),
            "observations": len(observations),
            "total_issues": len(issues),
            "open_issues": len(open_issues),
            "monitoring_issues": len(monitoring_issues),
            "resolved_issues": len(resolved_issues),
            "closed_issues": len(closed_issues),
            "resolved_today": resolved_today,
            "resolved_this_week": resolved_this_week,
            "founder_relevant_issues": len(founder_relevant),
            "leadership_relevant_issues": len(leadership_relevant),
            "team_relevant_issues": len(team_relevant),
            "critical_issues": len(critical_issues),
            "high_severity_events": high_severity,
        }
