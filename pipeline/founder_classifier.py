"""Deterministic founder-relevance classifier for events, issues, and findings.

This module implements rule-based classification that assigns:
- FounderImpact (WHY should the founder care?)
- FounderAttention (HOW urgently?)
- RelevanceLevel (WHO should see this?)

No LLM calls. Pure keyword + severity + duration logic.
"""

import logging
from datetime import datetime, timezone

from domain.enums import (
    EventType, FounderAttention, FounderImpact, RelevanceLevel, Severity,
)
from domain.models import Event, IntelligenceFinding, Issue
import config

logger = logging.getLogger(__name__)


# Severity ordering for comparison
_SEVERITY_RANK = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}

# Attention ordering for escalation
_ATTENTION_RANK = {
    FounderAttention.FYI: 0,
    FounderAttention.MONITOR: 1,
    FounderAttention.ACTION_REQUIRED: 2,
    FounderAttention.IMMEDIATE_ACTION: 3,
}

# EventType → default FounderImpact mapping
_EVENT_TYPE_IMPACT: dict[EventType, FounderImpact] = {
    EventType.CLIENT_ESCALATION: FounderImpact.CUSTOMER_RISK,
    EventType.CLIENT_REQUEST: FounderImpact.CUSTOMER_RISK,
    EventType.PRODUCTION_INCIDENT: FounderImpact.OPERATIONAL_RISK,
    EventType.INFRASTRUCTURE_ISSUE: FounderImpact.OPERATIONAL_RISK,
    EventType.ENVIRONMENT_ISSUE: FounderImpact.OPERATIONAL_RISK,
    EventType.DELIVERY_BLOCKED: FounderImpact.DELIVERY_RISK,
    EventType.RELEASE_DELAY: FounderImpact.DELIVERY_RISK,
    EventType.DEPENDENCY_WAIT: FounderImpact.DELIVERY_RISK,
    EventType.RESOURCE_CONSTRAINT: FounderImpact.TEAM_RISK,
    EventType.PERFORMANCE_DEGRADATION: FounderImpact.PRODUCT_RISK,
    EventType.QUALITY_CONCERN: FounderImpact.PRODUCT_RISK,
    EventType.RISK_INDICATOR: FounderImpact.UNKNOWN,
}


class FounderClassifier:
    """Deterministic classifier for founder impact, attention, and relevance.

    Uses a hierarchy of classification strategies:
    1. Keyword matching against title/description
    2. Event type mapping
    3. Severity-based fallback
    """

    def __init__(self) -> None:
        """Initialize the classifier with keyword maps from config."""
        self._impact_keywords: dict[str, list[str]] = config.FOUNDER_IMPACT_KEYWORDS
        self._noise_keywords: list[str] = config.NOISE_KEYWORDS
        self._team_keywords: list[str] = config.TEAM_LEVEL_KEYWORDS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_event(self, event: Event) -> Event:
        """Classify an event with founder impact, attention, and relevance.

        Args:
            event: The event to classify (modified in-place).

        Returns:
            The same event with founder fields populated.
        """
        combined_text = f"{event.title} {event.description}".lower()

        event.founder_impact = self._classify_impact(combined_text, event.event_type)
        event.relevance_level = self._classify_relevance(
            combined_text, event.severity, event.founder_impact
        )
        event.founder_attention = self._classify_attention(
            event.severity, event.founder_impact, event.relevance_level
        )

        return event

    def classify_issue(self, issue: Issue, report_date: str | None = None) -> Issue:
        """Classify an issue with founder impact, attention, and relevance.

        Also applies escalation logic based on days open and occurrence count.

        Args:
            issue: The issue to classify (modified in-place).
            report_date: Current date for escalation calculation (YYYY-MM-DD).

        Returns:
            The same issue with founder fields populated.
        """
        combined_text = f"{issue.title} {issue.summary}".lower()

        # Determine event_type from linked events or infer from text
        inferred_event_type = self._infer_event_type(combined_text)

        issue.founder_impact = self._classify_impact(combined_text, inferred_event_type)
        issue.relevance_level = self._classify_relevance(
            combined_text, issue.severity, issue.founder_impact
        )
        issue.founder_attention = self._classify_attention(
            issue.severity, issue.founder_impact, issue.relevance_level
        )

        # Apply escalation logic for open issues
        if report_date:
            self._apply_escalation(issue, report_date)

        return issue

    def classify_finding(self, finding: IntelligenceFinding) -> IntelligenceFinding:
        """Classify a finding with founder impact, attention, and relevance.

        Args:
            finding: The finding to classify (modified in-place).

        Returns:
            The same finding with founder fields populated.
        """
        combined_text = f"{finding.title} {finding.summary}".lower()
        inferred_event_type = self._infer_event_type(combined_text)

        finding.founder_impact = self._classify_impact(combined_text, inferred_event_type)
        finding.relevance_level = self._classify_relevance(
            combined_text, finding.severity, finding.founder_impact
        )
        finding.founder_attention = self._classify_attention(
            finding.severity, finding.founder_impact, finding.relevance_level
        )

        return finding

    # ------------------------------------------------------------------
    # Impact Classification
    # ------------------------------------------------------------------

    def _classify_impact(
        self, text: str, event_type: EventType | None = None
    ) -> FounderImpact:
        """Determine founder impact from text keywords and event type.

        Strategy:
        1. Scan text for keyword matches (most specific)
        2. Fall back to event type mapping
        3. Default to UNKNOWN
        """
        # Keyword-based classification (highest priority)
        best_match: FounderImpact | None = None
        best_match_count = 0

        for impact_name, keywords in self._impact_keywords.items():
            match_count = sum(1 for kw in keywords if kw in text)
            if match_count > best_match_count:
                best_match_count = match_count
                try:
                    best_match = FounderImpact(impact_name)
                except ValueError:
                    pass

        if best_match is not None and best_match_count > 0:
            return best_match

        # Event type fallback
        if event_type is not None and event_type in _EVENT_TYPE_IMPACT:
            return _EVENT_TYPE_IMPACT[event_type]

        return FounderImpact.UNKNOWN

    # ------------------------------------------------------------------
    # Relevance Classification
    # ------------------------------------------------------------------

    def _classify_relevance(
        self, text: str, severity: Severity, impact: FounderImpact
    ) -> RelevanceLevel:
        """Determine who should see this item.

        Strategy:
        1. Check for noise keywords → NOISE
        2. CRITICAL severity → always FOUNDER
        3. HIGH severity + meaningful impact → FOUNDER
        4. Revenue/customer/strategic at MEDIUM+ severity → FOUNDER
        5. Revenue/customer/strategic at LOW severity → LEADERSHIP
        6. Operational/delivery/product at MEDIUM → LEADERSHIP
        7. Team-level keywords → TEAM
        8. LOW severity → TEAM
        9. Remaining → TEAM
        """
        # Check for noise
        if self._is_noise(text, severity):
            return RelevanceLevel.NOISE

        # Check for team-level keywords first (regardless of impact)
        if severity == Severity.LOW:
            admin_keywords = {
                "credential request", "environment setup", "local build",
                "estimate", "status update", "standup", "sprint board",
                "ticket update", "follow up", "documentation", "wiki",
                "readme", "postman"
            }
            for kw in self._team_keywords:
                if kw in text:
                    if kw in admin_keywords:
                        return RelevanceLevel.NOISE
                    return RelevanceLevel.TEAM

        # CRITICAL severity → always FOUNDER
        if severity == Severity.CRITICAL:
            return RelevanceLevel.FOUNDER

        # Tighten HIGH severity relevance rule:
        # HIGH + TEAM_RISK/OPERATIONAL_RISK/DELIVERY_RISK/PRODUCT_RISK → LEADERSHIP, not FOUNDER
        if severity == Severity.HIGH and impact in (
            FounderImpact.TEAM_RISK,
            FounderImpact.OPERATIONAL_RISK,
            FounderImpact.DELIVERY_RISK,
            FounderImpact.PRODUCT_RISK,
        ):
            return RelevanceLevel.LEADERSHIP

        # HIGH severity with a meaningful impact → FOUNDER
        if severity == Severity.HIGH and impact != FounderImpact.UNKNOWN:
            return RelevanceLevel.FOUNDER

        # Founder-critical impacts: revenue, customer, strategic, compliance
        founder_critical_impacts = {
            FounderImpact.REVENUE_RISK,
            FounderImpact.CUSTOMER_RISK,
            FounderImpact.STRATEGIC_RISK,
            FounderImpact.COMPLIANCE_RISK,
        }

        if impact in founder_critical_impacts:
            # MEDIUM+ severity → FOUNDER
            if severity in (Severity.MEDIUM, Severity.HIGH):
                return RelevanceLevel.FOUNDER
            # LOW severity → still important but LEADERSHIP level
            return RelevanceLevel.LEADERSHIP

        # Operational/delivery/team/product impacts at MEDIUM → LEADERSHIP
        leadership_impacts = {
            FounderImpact.OPERATIONAL_RISK,
            FounderImpact.DELIVERY_RISK,
            FounderImpact.PRODUCT_RISK,
            FounderImpact.TEAM_RISK,
            FounderImpact.HIRING_RISK,
        }
        if impact in leadership_impacts:
            if severity == Severity.MEDIUM:
                return RelevanceLevel.LEADERSHIP
            if severity == Severity.LOW:
                return RelevanceLevel.TEAM

        # HIGH severity unknown impact → LEADERSHIP
        if severity == Severity.HIGH and impact == FounderImpact.UNKNOWN:
            return RelevanceLevel.LEADERSHIP

        # LOW severity with unknown impact → TEAM
        if severity == Severity.LOW:
            return RelevanceLevel.TEAM

        # MEDIUM severity with unknown impact → TEAM
        if severity == Severity.MEDIUM and impact == FounderImpact.UNKNOWN:
            return RelevanceLevel.TEAM

        # Check for team keywords
        for kw in self._team_keywords:
            if kw in text:
                return RelevanceLevel.TEAM

        return RelevanceLevel.TEAM

    def _is_noise(self, text: str, severity: Severity) -> bool:
        """Check if text is social noise."""
        if severity in (Severity.HIGH, Severity.CRITICAL):
            return False
        for kw in self._noise_keywords:
            if kw in text:
                return True
        return False

    # ------------------------------------------------------------------
    # Attention Classification
    # ------------------------------------------------------------------

    def _classify_attention(
        self,
        severity: Severity,
        impact: FounderImpact,
        relevance: RelevanceLevel,
    ) -> FounderAttention:
        """Determine how urgently the founder should act.

        Rules:
        - CRITICAL + any known impact → IMMEDIATE_ACTION
        - HIGH + revenue/customer/delivery → ACTION_REQUIRED
        - MEDIUM + recurring → MONITOR
        - LOW + minor → FYI
        - Non-FOUNDER relevance → cap at MONITOR
        """
        # CRITICAL severity always demands immediate action
        if severity == Severity.CRITICAL:
            return FounderAttention.IMMEDIATE_ACTION

        # HIGH severity with significant impact
        high_impact_set = {
            FounderImpact.REVENUE_RISK,
            FounderImpact.CUSTOMER_RISK,
            FounderImpact.DELIVERY_RISK,
            FounderImpact.OPERATIONAL_RISK,
        }
        if severity == Severity.HIGH and impact in high_impact_set:
            return FounderAttention.ACTION_REQUIRED

        if severity == Severity.HIGH:
            return FounderAttention.MONITOR

        # MEDIUM severity
        if severity == Severity.MEDIUM:
            if impact in high_impact_set:
                return FounderAttention.MONITOR
            return FounderAttention.FYI

        # LOW severity
        return FounderAttention.FYI

    # ------------------------------------------------------------------
    # Escalation Logic
    # ------------------------------------------------------------------

    def _apply_escalation(self, issue: Issue, report_date: str) -> None:
        """Escalate attention level for long-running or recurring issues.

        Rules:
        - Open > ESCALATION_DAYS_THRESHOLD_1 days → bump attention +1
        - Open > ESCALATION_DAYS_THRESHOLD_2 days → bump attention +2
        - occurrence_count >= 3 → bump attention +1
        - Multiple teams affected → bump attention +1

        Attention is capped at IMMEDIATE_ACTION.
        """
        from domain.enums import IssueStatus
        if issue.status not in (IssueStatus.OPEN, IssueStatus.MONITORING):
            return

        try:
            from datetime import date as date_type
            report_dt = datetime.fromisoformat(report_date).date()
        except (ValueError, TypeError):
            return

        days_open = (report_dt - issue.first_seen.date()).days
        if days_open < 0:
            days_open = 0

        escalation_bumps = 0

        # Time-based escalation
        if days_open >= config.ESCALATION_DAYS_THRESHOLD_2:
            escalation_bumps += 2
        elif days_open >= config.ESCALATION_DAYS_THRESHOLD_1:
            escalation_bumps += 1

        # Recurrence-based escalation
        if issue.occurrence_count >= 5:
            escalation_bumps += 2
        elif issue.occurrence_count >= 3:
            escalation_bumps += 1

        # Multi-area escalation
        if len(issue.affected_areas) >= 3:
            escalation_bumps += 1

        # Apply bumps
        if escalation_bumps > 0:
            current_rank = _ATTENTION_RANK.get(issue.founder_attention, 0)
            new_rank = min(current_rank + escalation_bumps, 3)
            attention_by_rank = {v: k for k, v in _ATTENTION_RANK.items()}
            new_attention = attention_by_rank.get(new_rank, FounderAttention.IMMEDIATE_ACTION)

            if _ATTENTION_RANK[new_attention] > _ATTENTION_RANK[issue.founder_attention]:
                logger.debug(
                    "Escalated issue '%s': %s → %s (days_open=%d, occurrences=%d)",
                    issue.title, issue.founder_attention.value,
                    new_attention.value, days_open, issue.occurrence_count
                )
                issue.founder_attention = new_attention

            # Fix escalation to bump relevance_level:
            # when attention reaches ACTION_REQUIRED, set relevance to LEADERSHIP
            # when IMMEDIATE_ACTION, set to FOUNDER
            if issue.founder_attention == FounderAttention.ACTION_REQUIRED:
                if issue.relevance_level in (RelevanceLevel.TEAM, RelevanceLevel.NOISE):
                    issue.relevance_level = RelevanceLevel.LEADERSHIP
            elif issue.founder_attention == FounderAttention.IMMEDIATE_ACTION:
                if issue.relevance_level in (RelevanceLevel.TEAM, RelevanceLevel.NOISE, RelevanceLevel.LEADERSHIP):
                    issue.relevance_level = RelevanceLevel.FOUNDER

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _infer_event_type(self, text: str) -> EventType | None:
        """Infer an EventType from text content for classification purposes."""
        type_keywords = {
            EventType.CLIENT_ESCALATION: ["client escalation", "customer complaint", "client unhappy"],
            EventType.CLIENT_REQUEST: ["client request", "client asked", "client wants"],
            EventType.PRODUCTION_INCIDENT: ["production incident", "outage", "production down", "500 error"],
            EventType.INFRASTRUCTURE_ISSUE: ["infrastructure", "server", "aws", "cloud"],
            EventType.ENVIRONMENT_ISSUE: ["staging", "environment", "database connection"],
            EventType.DELIVERY_BLOCKED: ["blocked", "blocker", "cannot proceed"],
            EventType.RELEASE_DELAY: ["release delay", "deployment delay", "deployment blocked"],
            EventType.DEPENDENCY_WAIT: ["waiting for", "depends on", "blocked by"],
            EventType.RESOURCE_CONSTRAINT: ["resource", "staffing", "capacity"],
            EventType.PERFORMANCE_DEGRADATION: ["performance", "latency", "slow"],
            EventType.QUALITY_CONCERN: ["quality", "bug", "defect", "regression"],
        }

        for event_type, keywords in type_keywords.items():
            for kw in keywords:
                if kw in text:
                    return event_type

        return None
