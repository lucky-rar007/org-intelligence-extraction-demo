"""Core domain models for the Organizational Event Intelligence Pipeline.

This module defines Pydantic v2 models representing the core entities
in the pipeline: Message, Thread, Event, Observation, Issue,
IntelligenceFinding, and FounderReport.
These models are pure domain structures without persistence or business logic.
"""

import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator

from domain.enums import (
    EventType, IntelligenceType, IssueStatus, ObservationType, Severity,
    FounderImpact, FounderAttention, RelevanceLevel, CommitmentStatus,
)


class Message(BaseModel):
    """Represents a single message within a conversation thread."""

    id: str = Field(description="Unique identifier for the message.")
    sender: str = Field(description="The sender of the message.")
    text: str = Field(description="The textual content of the message.")
    timestamp: datetime.datetime = Field(description="The timestamp when the message was sent.")
    reply_to: Optional[str] = Field(
        default=None,
        description="The ID of the message this is replying to, if applicable."
    )


class Thread(BaseModel):
    """Represents a conversation thread containing a series of messages."""

    id: str = Field(description="Unique identifier for the thread.")
    date: datetime.date = Field(description="The date of the conversation thread.")
    messages: list[Message] = Field(
        default_factory=list,
        description="List of messages belonging to the thread."
    )
    participants: list[str] = Field(
        default_factory=list,
        description="List of unique participant identifiers in this thread."
    )

    @property
    def thread_id(self) -> str:
        """Alias for the unique thread identifier."""
        return self.id

    @property
    def parent_message(self) -> Optional[Message]:
        """The parent message initiating the thread."""
        return self.messages[0] if self.messages else None

    @property
    def replies(self) -> list[Message]:
        """List of replies in the thread (excluding the parent message)."""
        return self.messages[1:] if len(self.messages) > 1 else []

    @property
    def created_at(self) -> Optional[datetime.datetime]:
        """Timestamp of the thread's first message."""
        return self.messages[0].timestamp if self.messages else None

    @property
    def updated_at(self) -> Optional[datetime.datetime]:
        """Timestamp of the thread's latest activity."""
        return self.messages[-1].timestamp if self.messages else None



class Event(BaseModel):
    """Represents a structured signal or event extracted from conversations."""

    id: str = Field(description="Unique identifier for the event.")
    title: str = Field(description="A short, descriptive title of the event.")
    description: str = Field(description="A detailed description of the extracted event.")
    event_type: EventType = Field(description="The category of the operational event.")
    severity: Severity = Field(description="The business impact severity of the event.")
    source_thread_id: str = Field(description="The identifier of the conversation thread source.")
    participants: list[str] = Field(
        default_factory=list,
        description="List of participants associated with the event."
    )
    affected_areas: list[str] = Field(
        default_factory=list,
        description="List of modules, systems, or business areas affected by this event."
    )
    status: IssueStatus = Field(
        default=IssueStatus.OPEN,
        description="The current lifecycle status of the event."
    )
    confidence_score: float = Field(
        description="Extraction confidence score from 0.0 to 1.0."
    )
    created_at: datetime.datetime = Field(description="Timestamp when the event was extracted.")

    # --- Founder Intelligence Fields ---
    founder_impact: FounderImpact = Field(
        default=FounderImpact.UNKNOWN,
        description="Why the founder should care about this event."
    )
    founder_attention: FounderAttention = Field(
        default=FounderAttention.FYI,
        description="How urgently the founder should act on this event."
    )
    relevance_level: RelevanceLevel = Field(
        default=RelevanceLevel.TEAM,
        description="Who should see this event (FOUNDER, LEADERSHIP, TEAM, NOISE)."
    )


class Observation(BaseModel):
    """Represents a weak organizational signal that is individually minor
    but becomes valuable when aggregated over time.

    Observations capture recurring patterns like credential requests,
    documentation confusion, ownership ambiguity, and coordination friction
    that should not be forced into Events but must not be discarded.
    """

    id: str = Field(description="Unique identifier for the observation.")
    title: str = Field(description="A short, descriptive title of the observation.")
    summary: str = Field(description="Detailed description of the observed signal.")
    observation_type: ObservationType = Field(
        description="The category of organizational signal."
    )
    severity: Severity = Field(
        default=Severity.LOW,
        description="The business impact severity of the observation."
    )
    first_seen: datetime.datetime = Field(
        description="Timestamp when this observation was first detected."
    )
    last_seen: datetime.datetime = Field(
        description="Timestamp of the most recent occurrence."
    )
    occurrence_count: int = Field(
        default=1,
        description="Total number of times this observation has been detected."
    )
    source_team: Optional[str] = Field(
        default=None,
        description="The team from which this observation originated."
    )
    source_channel: Optional[str] = Field(
        default=None,
        description="The channel or conversation context of the observation."
    )
    related_thread_ids: list[str] = Field(
        default_factory=list,
        description="Thread IDs where this observation was detected."
    )
    related_message_ids: list[str] = Field(
        default_factory=list,
        description="Message IDs associated with this observation."
    )


class Issue(BaseModel):
    """Represents a long-running problem aggregated across multiple events."""

    id: str = Field(description="Unique identifier for the tracked issue.")
    title: str = Field(description="A descriptive title for the issue.")
    summary: str = Field(description="A summary explaining the aggregated problem.")
    severity: Severity = Field(description="The overall business impact severity of the issue.")
    status: IssueStatus = Field(description="The current lifecycle state of the issue.")
    first_seen: datetime.datetime = Field(description="Timestamp of the earliest event linked to this issue.")
    last_seen: datetime.datetime = Field(description="Timestamp of the latest event linked to this issue.")
    occurrence_count: int = Field(description="Total occurrences of events linked to this issue.")
    affected_areas: list[str] = Field(
        default_factory=list,
        description="Systems, modules, or teams impacted by this issue."
    )
    linked_event_ids: list[str] = Field(
        default_factory=list,
        description="List of event IDs that are aggregated into this issue."
    )
    affected_team: Optional[str] = Field(
        default=None,
        description="Primary team affected by this issue."
    )
    affected_channel: Optional[str] = Field(
        default=None,
        description="Primary channel where this issue surfaces."
    )
    severity_history: list[dict[str, str]] = Field(
        default_factory=list,
        description="History of severity changes over time, each entry containing 'date' and 'severity'."
    )

    # --- Lifecycle Fields ---
    resolved_at: Optional[datetime.datetime] = Field(
        default=None,
        description="Timestamp when the issue was resolved."
    )
    resolution_summary: Optional[str] = Field(
        default=None,
        description="Description of how the issue was resolved."
    )
    resolution_evidence: list[str] = Field(
        default_factory=list,
        description="Event IDs that provided resolution evidence."
    )
    status_history: list[dict[str, str]] = Field(
        default_factory=list,
        description="History of status transitions: [{'date': ..., 'from': ..., 'to': ..., 'reason': ...}]."
    )

    resolved_by_event_id: Optional[str] = Field(
        default=None,
        description="The event ID that resolved this issue."
    )
    last_updated: Optional[datetime.datetime] = Field(
        default=None,
        description="Timestamp when the issue was last updated."
    )
    days_open: int = Field(
        default=0,
        description="Number of days the issue has been open."
    )
    normalized_title: Optional[str] = Field(
        default=None,
        description="Title stripped of low-information words (e.g. bug, delay)."
    )
    timeline_events: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Chronological timeline of event updates, state transitions, and escalations."
    )

    # --- Founder Intelligence Fields ---
    founder_impact: FounderImpact = Field(
        default=FounderImpact.UNKNOWN,
        description="Why the founder should care about this issue."
    )
    founder_attention: FounderAttention = Field(
        default=FounderAttention.FYI,
        description="How urgently the founder should act."
    )
    relevance_level: RelevanceLevel = Field(
        default=RelevanceLevel.TEAM,
        description="Who should see this issue (FOUNDER, LEADERSHIP, TEAM, NOISE)."
    )

    @property
    def days_stale(self) -> int:
        """Computes days since last_seen."""
        now = datetime.datetime.now(self.last_seen.tzinfo)
        return (now - self.last_seen).days


class IntelligenceFinding(BaseModel):
    """Represents higher-level organizational intelligence generated from events and observations."""

    id: str = Field(description="Unique identifier for the intelligence finding.")
    title: str = Field(description="Title summarizing the intelligence finding.")
    summary: str = Field(description="Detailed summary explaining the finding, impact, or trend.")
    severity: Severity = Field(description="The severity or business risk level of the finding.")
    supporting_event_ids: list[str] = Field(
        default_factory=list,
        description="List of event IDs that support or corroborate this finding."
    )
    related_issue_ids: list[str] = Field(
        default_factory=list,
        description="List of issue IDs related to this finding."
    )
    related_observation_ids: list[str] = Field(
        default_factory=list,
        description="List of observation IDs that contributed to this finding."
    )
    recommendation: str = Field(description="Actionable advice or remediation recommendation.")
    created_at: datetime.datetime = Field(description="Timestamp when the finding was generated.")
    finding_type: Optional[IntelligenceType] = Field(
        default=None,
        description="Optional category of the intelligence finding."
    )
    confidence_score: float = Field(
        default=0.0,
        description="Confidence score for this finding between 0.0 and 1.0."
    )
    evidence_count: int = Field(
        default=0,
        description="Total number of supporting evidence items (events + observations)."
    )

    # --- Founder Intelligence Fields ---
    founder_impact: FounderImpact = Field(
        default=FounderImpact.UNKNOWN,
        description="Why the founder should care about this finding."
    )
    founder_attention: FounderAttention = Field(
        default=FounderAttention.FYI,
        description="How urgently the founder should act."
    )
    relevance_level: RelevanceLevel = Field(
        default=RelevanceLevel.TEAM,
        description="Who should see this finding."
    )


class IssueCluster(BaseModel):
    """Represents a root-cause cluster grouping multiple related issues."""

    cluster_id: str = Field(description="Unique identifier for the cluster.")
    title: str = Field(description="Title of the cluster (e.g. Payment Gateway Problems).")
    summary: str = Field(description="A summary explaining the clustered problem.")
    business_area: str = Field(description="The primary business area impacted.")
    severity: Severity = Field(description="The highest severity among clustered issues.")
    status: IssueStatus = Field(description="The status of the cluster.")
    days_open: int = Field(default=0, description="How long the underlying business problem has existed.")
    first_seen: datetime.datetime = Field(description="Earliest timestamp across clustered issues.")
    last_seen: datetime.datetime = Field(description="Latest timestamp across clustered issues.")
    occurrence_count: int = Field(description="Total occurrences of events/issues linked to this cluster.")
    supporting_issue_ids: list[str] = Field(
        default_factory=list,
        description="List of issue IDs grouped under this cluster."
    )
    supporting_event_ids: list[str] = Field(
        default_factory=list,
        description="List of event IDs grouped under this cluster."
    )
    recommended_action: str = Field(description="Action recommendation for the founder.")
    owner_candidates: list[str] = Field(
        default_factory=list,
        description="List of candidates who can own resolving this cluster."
    )
    trend: str = Field(description="Trend status: NEW, STABLE, IMPROVING, WORSENING, RESOLVED.")
    risk_type: str = Field(description="The business risk classification type.")
    source_channels: list[str] = Field(
        default_factory=list,
        description="Communication channels where this cluster's issues surfaced."
    )
    source_teams: list[str] = Field(
        default_factory=list,
        description="Teams associated with this cluster."
    )
    confidence_score: float = Field(description="Confidence score for this cluster.")
    timeline: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Timeline of events for the cluster."
    )

    model_config = {
        "populate_by_name": True
    }

    @model_validator(mode='before')
    @classmethod
    def check_compat_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "cluster_title" in data and "title" not in data:
                data["title"] = data["cluster_title"]
            if "cluster_summary" in data and "summary" not in data:
                data["summary"] = data["cluster_summary"]
            if "related_issue_ids" in data and "supporting_issue_ids" not in data:
                data["supporting_issue_ids"] = data["related_issue_ids"]
        return data

    @property
    def cluster_title(self) -> str:
        return self.title

    @cluster_title.setter
    def cluster_title(self, value: str) -> None:
        self.title = value

    @property
    def cluster_summary(self) -> str:
        return self.summary

    @cluster_summary.setter
    def cluster_summary(self, value: str) -> None:
        self.summary = value

    @property
    def related_issue_ids(self) -> list[str]:
        return self.supporting_issue_ids

    @related_issue_ids.setter
    def related_issue_ids(self, value: list[str]) -> None:
        self.supporting_issue_ids = value


class Commitment(BaseModel):
    """Represents a promise or commitment made by a team member in conversation."""

    commitment_id: str = Field(description="Unique identifier for the commitment.")
    owner: str = Field(description="The person who made the promise (standardized first name).")
    description: str = Field(description="What was promised.")
    created_date: str = Field(description="The date the promise was made (YYYY-MM-DD).")
    due_date: str = Field(description="The due date for the promise (YYYY-MM-DD).")
    status: CommitmentStatus = Field(description="The current state of the commitment.")
    context: Optional[str] = Field(
        default=None,
        description="The message context or quote where the promise was made."
    )


class FounderActionable(BaseModel):
    """Represents an actionable recommendation for the founder."""

    actionable_id: str = Field(description="Unique identifier for the actionable recommendation.")
    title: str = Field(description="High-level executive title.")
    summary: str = Field(description="Why it matters to the business/founder.")
    risk_type: str = Field(description="The business risk type classification.")
    severity: Severity = Field(description="The rolled up business severity.")
    recommended_action: str = Field(description="The proposed mitigation or action.")
    supporting_cluster_ids: list[str] = Field(
        default_factory=list,
        description="List of cluster IDs contributing to this actionable."
    )
    supporting_issue_ids: list[str] = Field(
        default_factory=list,
        description="List of issue IDs contributing to this actionable."
    )
    supporting_event_ids: list[str] = Field(
        default_factory=list,
        description="List of event IDs contributing to this actionable."
    )
    confidence_score: float = Field(description="Rolled up confidence score between 0.0 and 1.0.")
    source_teams: list[str] = Field(
        default_factory=list,
        description="List of teams contributing to this actionable."
    )
    source_channels: list[str] = Field(
        default_factory=list,
        description="List of communication channels contributing to this actionable."
    )
    created_date: str = Field(description="The date this actionable was generated (YYYY-MM-DD).")
    priority_score: float = Field(description="Calculated priority score based on severity and recurrences.")


class ExecutiveConcern(BaseModel):
    """Represents a high-level executive concern rolling up operational clusters."""

    concern_id: str = Field(description="Unique identifier for the concern.")
    title: str = Field(description="Executive-level title of the concern.")
    risk_type: str = Field(description="The business risk classification type.")
    supporting_clusters: list[str] = Field(
        default_factory=list,
        description="Titles of supporting clusters."
    )
    severity: Severity = Field(description="Rolled up severity of the concern.")
    recommendation: str = Field(description="Action recommendation for the founder.")
    supporting_cluster_ids: list[str] = Field(
        default_factory=list,
        description="IDs of supporting clusters for future RAG retrieval."
    )


class FounderReport(BaseModel):
    """Represents a structured JSON report designed to power a founder/executive dashboard.

    This model generates structured JSON output (not markdown, not plain text).
    It is the final deliverable of the intelligence pipeline.
    """

    report_date: str = Field(description="The date covered by this report (YYYY-MM-DD).")
    generated_at: str = Field(description="ISO timestamp when the report was generated.")
    executive_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="High-level summary of the day's organizational signals."
    )
    executive_concerns: list[dict[str, Any]] = Field(
        default_factory=list,
        description="High-level synthesized executive concerns."
    )
    founder_actionables: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Rolled up actions recommended for the founder."
    )
    high_risk_clusters: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Primary tracked issue clusters."
    )
    critical_actionables: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Prioritized list of critical items requiring attention, sorted by attention > severity > recurrence."
    )
    open_issues: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Currently open tracked issues (retained for drill-down compatibility)."
    )
    monitoring_issues: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Issues in MONITORING state — fix applied, awaiting confirmation."
    )
    recently_resolved: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Issues resolved during the current reporting period."
    )
    intelligence_findings: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Pattern-based intelligence findings from events and observations."
    )
    people_risks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Personnel bottleneck and single-point-of-failure risks."
    )
    knowledge_risks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Knowledge concentration and silo risks."
    )
    commitment_risks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Analysis of commitment completion metrics and trends."
    )
    team_health_signals: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Process, alignment, and execution friction signals."
    )
    top_bottlenecks: list[str] = Field(
        default_factory=list,
        description="Names of individuals flagged as critical delivery bottlenecks."
    )
    top_dependency_nodes: list[str] = Field(
        default_factory=list,
        description="Names of critical engineering nodes whose absence blocks work."
    )
    commitments_due: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of commitments due on the report date."
    )
    overdue_commitments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of commitments currently overdue."
    )
    knowledge_concentration: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Key subsystems and their primary engineering dependencies."
    )
    issue_clusters: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Root cause issue clusters grouping duplicate tasks."
    )
    metrics: dict[str, int] = Field(
        default_factory=dict,
        description="Quantitative pipeline metrics for this run."
    )



