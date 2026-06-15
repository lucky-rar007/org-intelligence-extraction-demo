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


class IssueStatus(str, Enum):
    """Represents the lifecycle state of a tracked issue."""

    OPEN = "OPEN"
    """Issue is currently active."""

    RESOLVED = "RESOLVED"
    """Issue has been confirmed resolved."""

    STALE = "STALE"
    """Issue has not appeared for a long period and is considered inactive."""


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
