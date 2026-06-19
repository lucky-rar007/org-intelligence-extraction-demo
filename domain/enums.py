"""Domain-specific enumerations for the Organizational Event Intelligence Pipeline.

This module defines the primary enums used throughout the event intelligence pipeline
to categorize and track the states, severities, event types, and intelligence findings.
"""

from enum import Enum


class EventType(str, Enum):
    """Represents operational events extracted from conversation threads."""

    DELIVERY_BLOCKED = "DELIVERY_BLOCKED"
    DEPENDENCY_WAIT = "DEPENDENCY_WAIT"
    CLIENT_REQUEST = "CLIENT_REQUEST"
    CLIENT_ESCALATION = "CLIENT_ESCALATION"
    ENVIRONMENT_ISSUE = "ENVIRONMENT_ISSUE"
    INFRASTRUCTURE_ISSUE = "INFRASTRUCTURE_ISSUE"
    RESOURCE_CONSTRAINT = "RESOURCE_CONSTRAINT"
    RELEASE_DELAY = "RELEASE_DELAY"
    QUALITY_CONCERN = "QUALITY_CONCERN"
    PERFORMANCE_DEGRADATION = "PERFORMANCE_DEGRADATION"
    PRODUCTION_INCIDENT = "PRODUCTION_INCIDENT"
    RISK_INDICATOR = "RISK_INDICATOR"


class ObservationType(str, Enum):
    """Represents weak organizational signals that are individually minor but cumulatively valuable."""

    KNOWLEDGE_GAP = "KNOWLEDGE_GAP"
    """Repeated questions about known processes, tools, or systems."""

    COORDINATION_FRICTION = "COORDINATION_FRICTION"
    """Recurring sync issues, handoff confusion, or cross-team alignment problems."""

    PROCESS_COMPLIANCE = "PROCESS_COMPLIANCE"
    """Reminders about standup attendance, ticket updates, or workflow adherence."""

    OWNERSHIP_CONFUSION = "OWNERSHIP_CONFUSION"
    """Ambiguity about who owns a module, decision, or deliverable."""

    DEPENDENCY_WAITING = "DEPENDENCY_WAITING"
    """Repeated requests for access, credentials, or blocked-by-other-team signals."""

    DOCUMENTATION_GAP = "DOCUMENTATION_GAP"
    """Missing, outdated, or hard-to-find documentation causing repeated questions."""

    RESOURCE_CONTENTION = "RESOURCE_CONTENTION"
    """Shared resources (environments, tools, people) causing friction."""

    COMMUNICATION_PATTERN = "COMMUNICATION_PATTERN"
    """Notable communication patterns such as escalation chains or information silos."""

    OTHER = "OTHER"
    """Observation that does not fit established categories."""


class IssueStatus(str, Enum):
    """Represents the lifecycle state of a tracked issue.

    Lifecycle flow:
        OPEN → MONITORING → RESOLVED → CLOSED
        OPEN → RESOLVED (direct when explicit resolution evidence exists)
    """

    OPEN = "OPEN"
    """Issue is currently active and unresolved. Needs attention."""

    MONITORING = "MONITORING"
    """Evidence suggests issue is being fixed. Waiting for confirmation.
    Should not appear in founder critical lists."""

    RESOLVED = "RESOLVED"
    """Explicit evidence of resolution found. Remains for historical tracking."""

    CLOSED = "CLOSED"
    """Archived issue. No longer operationally relevant."""


class Severity(str, Enum):
    """Represents business impact."""

    LOW = "LOW"
    """Informational or minor friction."""

    MEDIUM = "MEDIUM"
    """Team-level impact."""

    HIGH = "HIGH"
    """Delivery or customer impact."""

    CRITICAL = "CRITICAL"
    """Production outage, severe client escalation, or major business risk."""


class FounderImpact(str, Enum):
    """Classifies WHY the founder should care about this item.

    Every event, issue, and finding should be tagged with one of these
    to answer: 'Why does this matter to the founder?'
    """

    REVENUE_RISK = "REVENUE_RISK"
    """Revenue delay, lost account, billing issue, payment failure."""

    CUSTOMER_RISK = "CUSTOMER_RISK"
    """Client escalation, churn concern, dissatisfaction signal."""

    DELIVERY_RISK = "DELIVERY_RISK"
    """Deployment blocked, release delay, critical dependency."""

    TEAM_RISK = "TEAM_RISK"
    """Team health, burnout, conflict, capacity concern."""

    HIRING_RISK = "HIRING_RISK"
    """Hiring bottleneck, missing staffing, key person dependency."""

    OPERATIONAL_RISK = "OPERATIONAL_RISK"
    """Infrastructure failure, database outage, cloud issue, security incident."""

    STRATEGIC_RISK = "STRATEGIC_RISK"
    """Major roadmap decision, market pivot, partnership opportunity."""

    COMPLIANCE_RISK = "COMPLIANCE_RISK"
    """Regulatory, legal, or compliance concern."""

    PRODUCT_RISK = "PRODUCT_RISK"
    """Product quality, UX degradation, feature regression."""

    UNKNOWN = "UNKNOWN"
    """Impact category cannot be determined."""


class FounderAttention(str, Enum):
    """Classifies HOW urgently the founder should act.

    Determines placement and prominence in the founder dashboard.
    """

    FYI = "FYI"
    """Low priority. Informational only. No action needed."""

    MONITOR = "MONITOR"
    """Worth watching. May escalate. Check periodically."""

    ACTION_REQUIRED = "ACTION_REQUIRED"
    """Needs founder decision or intervention soon."""

    IMMEDIATE_ACTION = "IMMEDIATE_ACTION"
    """Critical. Requires immediate founder attention."""


class RelevanceLevel(str, Enum):
    """Classifies WHO should see this item.

    Controls visibility across different dashboard levels.
    """

    FOUNDER = "FOUNDER"
    """Visible on the founder/executive dashboard. Highest relevance."""

    LEADERSHIP = "LEADERSHIP"
    """Visible to leadership (VPs, directors). Not in founder critical view."""

    TEAM = "TEAM"
    """Team-level visibility. Engineering leads and managers."""

    NOISE = "NOISE"
    """Social noise. Filtered from all operational dashboards."""


class IntelligenceType(str, Enum):
    """Represents findings produced by the aggregation layer."""

    RECURRING_ISSUE = "RECURRING_ISSUE"
    """Frequently occurring unresolved issue."""

    GROWING_ISSUE = "GROWING_ISSUE"
    """Issue increasing in frequency over time."""

    CLIENT_PRESSURE = "CLIENT_PRESSURE"
    """Elevated client requests or escalations."""

    DELIVERY_RISK = "DELIVERY_RISK"
    """Threat to delivery timelines."""

    OPERATIONAL_RISK = "OPERATIONAL_RISK"
    """Infrastructure, environment, or process concerns."""

    CRITICAL_INCIDENT = "CRITICAL_INCIDENT"
    """Severe incident requiring immediate attention."""


class CommitmentStatus(str, Enum):
    """Represents the lifecycle state of a tracked commitment."""
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    OVERDUE = "OVERDUE"
