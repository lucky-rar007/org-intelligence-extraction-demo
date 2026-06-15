"""Core domain models for the Organizational Event Intelligence Pipeline.

This module defines Pydantic v2 models representing the core entities
in the pipeline: Message, Thread, Event, Issue, IntelligenceFinding, and Report.
These models are pure domain structures without persistence or business logic.
"""

import datetime
from typing import Optional
from pydantic import BaseModel, Field

from domain.enums import EventType, IntelligenceType, IssueStatus, Severity


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


class IntelligenceFinding(BaseModel):
    """Represents higher-level organizational intelligence generated from events."""

    id: str = Field(description="Unique identifier for the intelligence finding.")
    title: str = Field(description="Title summarizing the intelligence finding.")
    summary: str = Field(description="Detailed summary explaining the finding, impact, or trend.")
    severity: Severity = Field(description="The severity or business risk level of the finding.")
    supporting_event_ids: list[str] = Field(
        default_factory=list,
        description="List of event IDs that support or corroborate this finding."
    )
    recommendation: str = Field(description="Actionable advice or remediation recommendation.")
    created_at: datetime.datetime = Field(description="Timestamp when the finding was generated.")
    finding_type: Optional[IntelligenceType] = Field(
        default=None,
        description="Optional category of the intelligence finding."
    )


class Report(BaseModel):
    """Represents a generated daily intelligence report compiling findings and metrics."""

    date: datetime.date = Field(description="The date covered by the intelligence report.")
    event_count: int = Field(description="Total number of events analyzed during this day.")
    issue_count: int = Field(description="Total number of active/resolved issues tracked.")
    intelligence_findings: list[IntelligenceFinding] = Field(
        default_factory=list,
        description="List of intelligence findings generated for the report."
    )
    critical_issues: list[str] = Field(
        default_factory=list,
        description="List of identifiers or titles of critical issues requiring immediate attention."
    )
    executive_summary: str = Field(description="High-level written summary of the day's events and findings.")
    generated_at: datetime.datetime = Field(description="Timestamp when the report was generated.")
