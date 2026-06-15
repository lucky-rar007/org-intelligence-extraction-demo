"""Pydantic schemas for data validation and LLM response contracts.

This module defines the validation schemas and contracts used for structured LLM outputs
and temporary data transformation within the Organizational Intelligence Extraction pipeline.
These schemas are separate from the core domain entities defined in domain.models.
"""

from pydantic import BaseModel, Field
from domain.enums import EventType, IssueStatus, Severity


class ExtractedEvent(BaseModel):
    """Represents a single event returned by the LLM during event extraction."""

    title: str = Field(description="A short, descriptive title of the extracted event.")
    description: str = Field(description="Detailed explanation of the extracted event.")
    event_type: EventType = Field(description="The categorized type of the operational event.")
    severity: Severity = Field(description="The business impact severity of the event.")
    status: IssueStatus = Field(
        default=IssueStatus.OPEN,
        description="The initial or current lifecycle status of the event."
    )
    participants: list[str] = Field(
        default_factory=list,
        description="List of participants involved in or associated with this event."
    )
    affected_areas: list[str] = Field(
        default_factory=list,
        description="Specific systems, teams, modules, or client accounts affected by the event."
    )
    confidence_score: float = Field(
        description="The LLM's confidence score in the extraction, which must be between 0.0 and 1.0.",
        ge=0.0,
        le=1.0
    )


class EventExtractionResponse(BaseModel):
    """Represents the complete response contract returned by the event extraction prompt."""

    events: list[ExtractedEvent] = Field(
        default_factory=list,
        description="A list of successfully extracted events from the source conversation thread."
    )


class IssueMatchResponse(BaseModel):
    """Represents the LLM response when determining if a new event matches an existing issue."""

    is_match: bool = Field(description="Indicates whether the event matches an existing issue.")
    issue_id: str | None = Field(
        default=None,
        description="The ID of the matching issue. This field is null if is_match is false."
    )
    reason: str = Field(description="Detailed reasoning for the matching or non-matching decision.")


class FindingCandidate(BaseModel):
    """Represents a candidate intelligence finding generated from aggregated events."""

    title: str = Field(description="Title of the high-level intelligence finding.")
    summary: str = Field(description="Summary of the finding's context, impact, or trend.")
    severity: Severity = Field(description="The business risk severity of the strategic finding.")
    recommendation: str = Field(description="An actionable mitigation or resolution recommendation.")
    supporting_event_ids: list[str] = Field(
        default_factory=list,
        description="List of event IDs that support or corroborate this candidate finding."
    )


class IntelligenceFindingResponse(BaseModel):
    """Represents the complete response contract from an intelligence aggregation prompt."""

    findings: list[FindingCandidate] = Field(
        default_factory=list,
        description="A list of candidate intelligence findings generated during aggregation."
    )


class ExecutiveSummaryResponse(BaseModel):
    """Represents the executive summary generated for a daily report."""

    summary: str = Field(description="The written executive summary narrative.")


class IssueSummaryResponse(BaseModel):
    """Represents a generated narrative summary for a tracked long-running issue."""

    summary: str = Field(description="The generated narrative summary of the issue.")
