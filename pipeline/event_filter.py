"""Classifies extracted events into actionable Events and Observations.

This module implements the signal classification layer that separates
high-impact actionable events from weak organizational signals (observations).
Observations are never discarded — they are stored for pattern detection
and intelligence aggregation.

Classification is rule-based using event_type and severity:
- HIGH/CRITICAL severity + actionable event types → Event
- LOW severity signals, process/coordination patterns → Observation
- MEDIUM severity uses event_type to decide

Phase 2 addition: Founder classification is applied to all events and observations.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from domain.enums import EventType, ObservationType, Severity
from domain.models import Event, Observation
from pipeline.founder_classifier import FounderClassifier
from utils.hashing import generate_id
import config

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Contains the classified output of the event filter.

    Attributes:
        events: Actionable events that warrant immediate attention.
        observations: Weak signals to be stored for pattern detection.
    """
    events: list[Event] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)


# Mapping from EventType to ObservationType for signals that should be observations
_EVENT_TO_OBSERVATION_TYPE: dict[str, ObservationType] = {
    EventType.DEPENDENCY_WAIT.value: ObservationType.DEPENDENCY_WAITING,
    EventType.RESOURCE_CONSTRAINT.value: ObservationType.RESOURCE_CONTENTION,
    EventType.QUALITY_CONCERN.value: ObservationType.PROCESS_COMPLIANCE,
    EventType.RISK_INDICATOR.value: ObservationType.COORDINATION_FRICTION,
}

# Keywords in event titles/descriptions that suggest observation-level signals
_OBSERVATION_KEYWORDS: list[str] = [
    "reminder", "standup", "follow up", "follow-up", "followup",
    "credential", "access request", "permission request",
    "documentation", "wiki", "confluence", "readme",
    "ownership", "who owns", "responsible for",
    "waiting for", "blocked by", "depends on",
    "confusion", "unclear", "ambiguous",
    "process", "compliance", "ticket update",
    "estimate", "status update",
    "planning", "board update", "sprint board",
]


class EventFilter:
    """Rule-based classifier that separates actionable Events from Observations.

    The filter applies the following logic:
    1. HIGH/CRITICAL severity events with actionable types → always Event
    2. LOW severity signals → Observation (unless actionable type)
    3. MEDIUM severity → Event if actionable type, else Observation
    4. Keyword-based detection for common observation patterns

    After classification, founder impact/attention/relevance is assigned to all events.
    """

    def __init__(self) -> None:
        """Initialize the EventFilter with actionable type configuration."""
        self._actionable_types: set[str] = set(config.EVENT_FILTER_ACTIONABLE_TYPES)
        self._classifier = FounderClassifier()

    def filter_events(self, events: list[Event]) -> FilterResult:
        """Classify a list of extracted events into actionable Events and Observations.

        Args:
            events: Raw events from the event extractor.

        Returns:
            A FilterResult containing separated events and observations.
        """
        result = FilterResult()

        for event in events:
            if self._is_social_noise(event):
                logger.info("Filtered out casual social noise: '%s'", event.title)
                continue
            if self._is_actionable(event):
                # Apply founder classification
                self._classifier.classify_event(event)
                result.events.append(event)
            else:
                observation = self._convert_to_observation(event)
                result.observations.append(observation)

        logger.info(
            "Filter result: %d actionable events, %d observations (from %d total signals)",
            len(result.events), len(result.observations), len(events)
        )
        return result

    def _is_social_noise(self, event: Event) -> bool:
        """Identify if an event is casual social noise (e.g. food orders, movie plans, sports)."""
        noise_keywords = {
            "eatfit", "toit", "dinner", "lunch", "breakfast", "cricket", "movie", "movies",
            "birthday", "restaurant", "food order", "social", "weekend", "drinks", "party"
        }
        combined_text = f"{event.title} {event.description}".lower()
        if event.severity in (Severity.LOW, Severity.MEDIUM):
            for kw in noise_keywords:
                if kw in combined_text:
                    return True
        return False

    def _is_actionable(self, event: Event) -> bool:
        """Determine if an event is actionable (should remain an Event).

        Args:
            event: The event to classify.

        Returns:
            True if the event should be retained as an actionable Event.
        """
        # CRITICAL and HIGH severity events are always actionable
        if event.severity in (Severity.CRITICAL, Severity.HIGH):
            return True

        # Check for observation keywords in title/description (keyword check runs before event_type check)
        combined_text = f"{event.title} {event.description}".lower()
        for keyword in _OBSERVATION_KEYWORDS:
            if keyword in combined_text:
                return False

        # Events with actionable types are always actionable regardless of severity
        if event.event_type.value in self._actionable_types:
            return True

        # MEDIUM severity without keyword matches stays as event
        if event.severity == Severity.MEDIUM:
            # Check if the event type maps to an observation type
            if event.event_type.value in _EVENT_TO_OBSERVATION_TYPE:
                return False
            return True

        # LOW severity defaults to observation
        if event.severity == Severity.LOW:
            return False

        return True

    def _classify_observation_type(self, event: Event) -> ObservationType:
        """Determine the ObservationType for an event being converted to an observation.

        Args:
            event: The event being converted.

        Returns:
            The most appropriate ObservationType.
        """
        # Direct mapping from event type
        if event.event_type.value in _EVENT_TO_OBSERVATION_TYPE:
            return _EVENT_TO_OBSERVATION_TYPE[event.event_type.value]

        # Keyword-based classification
        combined_text = f"{event.title} {event.description}".lower()

        if any(kw in combined_text for kw in ["credential", "access", "permission"]):
            return ObservationType.KNOWLEDGE_GAP

        if any(kw in combined_text for kw in ["documentation", "wiki", "confluence", "readme"]):
            return ObservationType.DOCUMENTATION_GAP

        if any(kw in combined_text for kw in ["ownership", "who owns", "responsible"]):
            return ObservationType.OWNERSHIP_CONFUSION

        if any(kw in combined_text for kw in ["waiting", "blocked by", "depends on"]):
            return ObservationType.DEPENDENCY_WAITING

        if any(kw in combined_text for kw in ["reminder", "standup", "follow up", "followup"]):
            return ObservationType.PROCESS_COMPLIANCE

        if any(kw in combined_text for kw in ["confusion", "unclear", "ambiguous"]):
            return ObservationType.COORDINATION_FRICTION

        if any(kw in combined_text for kw in ["process", "compliance", "ticket", "estimate"]):
            return ObservationType.PROCESS_COMPLIANCE

        return ObservationType.OTHER

    def _convert_to_observation(self, event: Event) -> Observation:
        """Convert an Event to an Observation domain object.

        Args:
            event: The event to convert.

        Returns:
            An Observation domain object preserving the signal information.
        """
        observation_type = self._classify_observation_type(event)
        now = datetime.now(timezone.utc)

        observation = Observation(
            id=generate_id("obs", event.title, event.event_type.value),
            title=event.title,
            summary=event.description,
            observation_type=observation_type,
            severity=event.severity,
            first_seen=event.created_at,
            last_seen=event.created_at,
            occurrence_count=1,
            source_team=event.affected_areas[0] if event.affected_areas else None,
            source_channel=None,
            related_thread_ids=[event.source_thread_id],
            related_message_ids=[],
        )

        logger.debug(
            "Converted event '%s' to observation (type=%s)",
            event.title, observation_type.value
        )
        return observation
