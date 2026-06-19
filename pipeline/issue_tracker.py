"""Identifies, tracks, and groups recurring issues across threads.

Implements persistent issue tracking with deterministic matching based on
title similarity and event type. Supports idempotent processing to prevent
duplicate issue updates when the pipeline is run multiple times for the same date.

Phase 1 additions:
- Issue lifecycle state machine (OPEN → MONITORING → RESOLVED → CLOSED)
- Automatic resolution detection from event text
- Status transition tracking with history
- Founder classification integration (Phase 2)
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from domain.enums import EventType, IssueStatus, Severity, FounderImpact, FounderAttention, RelevanceLevel
from domain.models import Event, Issue, Thread
from pipeline.founder_classifier import FounderClassifier
from pipeline.org_intelligence import normalize_name
from pipeline.resolution_detector import ResolutionDetector, ResolutionDetectionResult
from storage.issue_store import IssueStore
from utils.hashing import generate_id
from utils.similarity import are_similar, normalize_text, title_similarity
import config

logger = logging.getLogger(__name__)


# Resolution keywords — phrases that indicate an issue has been resolved
_RESOLUTION_KEYWORDS: list[str] = config.RESOLUTION_KEYWORDS

# Monitoring keywords — phrases that indicate a fix is in progress
_MONITORING_KEYWORDS: list[str] = config.MONITORING_KEYWORDS


def normalize_issue_title(title: str) -> str:
    """Normalize issue title by removing low-information words."""
    cleaned = title.lower()
    cleaned = re.sub(r'[^\w\s\-]', ' ', cleaned)
    low_info_words = {
        "issue", "problem", "bug", "error", "failure", "delay", "blocked",
        "blocker", "task", "request", "ticket", "update", "follow-up", "discussion"
    }
    words = cleaned.split()
    filtered = [w for w in words if w not in low_info_words]
    return " ".join(filtered).strip()


class IssueTracker:
    """Tracks recurring issues by matching new events against existing issues.

    Uses deterministic matching (normalized title similarity + event type)
    before creating new issues. Supports idempotent processing via date tracking.

    Lifecycle state machine:
        OPEN → MONITORING → RESOLVED → CLOSED
        OPEN → RESOLVED (direct when explicit evidence exists)
    """

    def __init__(self, issue_store: IssueStore | None = None) -> None:
        """Initialize the IssueTracker.

        Args:
            issue_store: Storage backend for issues. Defaults to a new IssueStore.
        """
        self.issue_store = issue_store or IssueStore()
        self._issues: list[Issue] = self.issue_store.load_issues()
        self._classifier = FounderClassifier()

    def process_events(self, events: list[Event], report_date: str, threads: list[Thread] | None = None) -> list[Issue]:
        """Process a batch of events and update the issue tracker.

        For each event:
        1. Check if the event is a resolution/monitoring signal for an existing issue
        2. Attempts to match against existing issues using title similarity and entity boost
        3. Updates matched issues (last_seen, occurrence_count, severity_history)
        4. Creates new issues for unmatched events

        After processing:
        - Applies founder classification to all issues
        - Applies escalation logic to long-running issues
        - Updates days_open and last_updated fields for all issues

        Args:
            events: List of actionable Event domain objects.
            report_date: The date being processed (YYYY-MM-DD format).
            threads: Optional list of raw thread objects for message-level evidence.

        Returns:
            The complete list of tracked issues after processing.
        """
        # Idempotency check — skip if this date has already been processed
        if self.issue_store.is_date_processed(report_date):
            logger.info(
                "Date %s has already been processed for issue tracking. Skipping to preserve idempotency.",
                report_date
            )
            return self._issues

        # Call raw message resolution scan at the start of processing if threads are provided
        if threads:
            self._scan_threads_for_resolutions(threads, report_date)

        if not events:
            logger.info("No events to process for issue tracking.")
            # Still apply escalation and updates to existing issues
            self._apply_escalation_to_all(report_date)
            self._apply_classification_to_all(report_date)
            self._update_all_days_open_and_last_updated(report_date)
            self.issue_store.save_issues(self._issues)
            return self._issues

        thread_map = {t.id: t for t in threads} if threads else {}
        detector = ResolutionDetector()

        new_issues_count = 0
        updated_issues_count = 0
        resolved_count = 0
        monitoring_count = 0

        for event in events:
            # Find matching thread if available
            thread = thread_map.get(event.source_thread_id)

            # Step 1: Check if this event is a resolution signal
            res_result = detector.detect_resolution(event, thread)

            if res_result.is_resolution:
                # Step 2: Smarter resolution matching
                matched_issue = self._find_matching_issue_for_resolution(event)
                if matched_issue is not None:
                    if res_result.target_status == IssueStatus.RESOLVED:
                        self._transition_to_resolved(matched_issue, event, report_date, res_result)
                        resolved_count += 1
                    elif res_result.target_status == IssueStatus.MONITORING:
                        # Only transition OPEN -> MONITORING. Never transition backwards automatically.
                        if matched_issue.status == IssueStatus.OPEN:
                            self._transition_to_monitoring(matched_issue, event, report_date, res_result)
                            monitoring_count += 1
                else:
                    # Resolution event with no matching active issue.
                    # Rule: DO NOT create a new issue.
                    logger.info("Resolution event '%s' did not match any active issue. Skipping.", event.title)
                continue

            # Step 3: Normal event processing (non-resolution event)
            matched_issue = self._find_matching_issue(event)

            if matched_issue is not None:
                self._update_issue(matched_issue, event, report_date)
                updated_issues_count += 1
            else:
                new_issue = self._create_issue(event, report_date)
                self._issues.append(new_issue)
                new_issues_count += 1

        # Apply escalation, classification, days_open and last_updated
        self._apply_escalation_to_all(report_date)
        self._apply_classification_to_all(report_date)
        self._update_all_days_open_and_last_updated(report_date)

        # Persist updated issues and mark date as processed
        self.issue_store.save_issues(self._issues)
        self.issue_store.mark_date_processed(report_date)

        logger.info(
            "Issue tracking complete for %s: %d new, %d updated, %d resolved, "
            "%d monitoring, %d total issues",
            report_date, new_issues_count, updated_issues_count,
            resolved_count, monitoring_count, len(self._issues)
        )
        return self._issues

    def get_open_issues(self) -> list[Issue]:
        """Retrieve all issues with OPEN status.

        Returns:
            A list of issues that are currently active.
        """
        return [
            issue for issue in self._issues
            if issue.status == IssueStatus.OPEN
        ]

    def get_monitoring_issues(self) -> list[Issue]:
        """Retrieve all issues with MONITORING status.

        Returns:
            A list of issues being monitored.
        """
        return [
            issue for issue in self._issues
            if issue.status == IssueStatus.MONITORING
        ]

    def get_resolved_issues(self) -> list[Issue]:
        """Retrieve all issues with RESOLVED status.

        Returns:
            A list of resolved issues.
        """
        return [
            issue for issue in self._issues
            if issue.status == IssueStatus.RESOLVED
        ]

    def get_active_issues(self) -> list[Issue]:
        """Retrieve all OPEN or MONITORING issues.

        Returns:
            A list of issues that are still active (not resolved/closed).
        """
        return [
            issue for issue in self._issues
            if issue.status in (IssueStatus.OPEN, IssueStatus.MONITORING)
        ]

    def get_all_issues(self) -> list[Issue]:
        """Retrieve all tracked issues regardless of status.

        Returns:
            The complete list of tracked issues.
        """
        return list(self._issues)

    # ------------------------------------------------------------------
    # Resolution Detection & Smarter Matching
    # ------------------------------------------------------------------

    def _get_cleaned_title(self, title: str) -> str:
        """Helper to remove resolution/monitoring keywords and special characters from a title."""
        cleaned = title.lower()
        for kw in _RESOLUTION_KEYWORDS + _MONITORING_KEYWORDS:
            cleaned = cleaned.replace(kw, "")
        cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
        cleaned = " ".join(cleaned.split())
        return cleaned

    def _find_matching_issue_for_resolution(self, event: Event) -> Issue | None:
        """Find an existing active issue that this resolution event matches.

        Uses title cleaning, stop-word removal, and boost rules for shared entities
        to perform extremely robust matching.

        Args:
            event: The resolution event.

        Returns:
            The matching issue, or None.
        """
        best_match: Issue | None = None
        best_score: float = 0.0
        cleaned_event_title = self._get_cleaned_title(event.title)
        event_norm = normalize_issue_title(cleaned_event_title)

        for issue in self._issues:
            # Only match against active issues
            if issue.status not in (IssueStatus.OPEN, IssueStatus.MONITORING):
                continue

            cleaned_issue_title = self._get_cleaned_title(issue.title)
            issue_norm = issue.normalized_title or normalize_issue_title(cleaned_issue_title)

            # Calculate similarities
            score_full = title_similarity(event_norm, issue_norm)
            score_desc = title_similarity(normalize_issue_title(event.description[:100]), issue_norm)

            similarity = max(score_full, score_desc)

            # Shared entities/clients boost
            shared_entities = []
            entities_to_check = [
                "client abc", "client xyz",
                "payment gateway", "paytm", "gateway", "checkout",
                "webhook", "redis", "cors", "csv export", "analytics api",
                "android", "mobile", "font scaling", "composite index",
                "staging database", "android app", "ios app", "app crash",
                "webhook incident", "redis retry", "backend", "dashboard"
            ]

            event_lower = event.title.lower()
            issue_lower = issue.title.lower()

            for ent in entities_to_check:
                if ent in event_lower and ent in issue_lower:
                    shared_entities.append(ent)

            if shared_entities:
                similarity += 0.35 * len(shared_entities)

            has_client = ("client abc" in event_lower and "client abc" in issue_lower) or \
                         ("client xyz" in event_lower and "client xyz" in issue_lower)
            if has_client:
                similarity += 0.40

            similarity = min(similarity, 1.5)

            threshold = config.RESOLUTION_SIMILARITY_THRESHOLD
            if similarity >= threshold and similarity > best_score:
                best_score = similarity
                best_match = issue

        if best_match is not None:
            logger.info(
                "Smarter resolution match: event '%s' → issue '%s' (score=%.3f)",
                event.title, best_match.title, best_score
            )

        return best_match

    # ------------------------------------------------------------------
    # State Transitions
    # ------------------------------------------------------------------

    def _transition_to_monitoring(self, issue: Issue, event: Event, report_date: str, result: ResolutionDetectionResult) -> None:
        """Transition an issue from OPEN to MONITORING.

        Args:
            issue: The issue to transition.
            event: The event that triggered the transition.
            report_date: The processing date.
            result: The resolution detection result containing evidence.
        """
        old_status = issue.status
        issue.status = IssueStatus.MONITORING
        issue.last_seen = event.created_at
        issue.last_updated = datetime.now(timezone.utc)

        if event.id not in issue.linked_event_ids:
            issue.linked_event_ids.append(event.id)

        evidence_msg = ""
        if result.evidence_text:
            evidence_msg = f' Message: "{result.evidence_text}" by {result.evidence_author} (confidence: {result.resolution_confidence:.2f}).'

        reason = f"Monitoring signal: {event.title[:80]}.{evidence_msg}"
        issue.status_history.append({
            "date": report_date,
            "from": old_status.value,
            "to": IssueStatus.MONITORING.value,
            "reason": reason,
        })

        issue.timeline_events.append({
            "date": report_date,
            "event": "STATUS_TRANSITION",
            "from": old_status.value,
            "to": IssueStatus.MONITORING.value,
            "reason": reason,
        })

        logger.info(
            "Issue '%s' transitioned: %s → MONITORING (trigger: '%s')",
            issue.title, old_status.value, event.title
        )

    def _transition_to_resolved(self, issue: Issue, event: Event, report_date: str, result: ResolutionDetectionResult) -> None:
        """Transition an issue to RESOLVED.

        Args:
            issue: The issue to resolve.
            event: The event providing resolution evidence.
            report_date: The processing date.
            result: The resolution detection result containing evidence.
        """
        old_status = issue.status
        issue.status = IssueStatus.RESOLVED
        issue.last_seen = event.created_at
        issue.resolved_at = event.created_at
        issue.resolved_by_event_id = event.id
        issue.last_updated = datetime.now(timezone.utc)

        # Build explanation of why issue was closed
        evidence_msg = ""
        if result.evidence_text:
            evidence_msg = f' Message: "{result.evidence_text}" by {result.evidence_author} (confidence: {result.resolution_confidence:.2f}).'

        issue.resolution_summary = (
            f"Resolved by Event: {event.title}.{evidence_msg}"
        )

        if event.id not in issue.resolution_evidence:
            issue.resolution_evidence.append(event.id)

        if event.id not in issue.linked_event_ids:
            issue.linked_event_ids.append(event.id)

        reason = f"Resolution evidence: {event.title[:80]}.{evidence_msg}"
        issue.status_history.append({
            "date": report_date,
            "from": old_status.value,
            "to": IssueStatus.RESOLVED.value,
            "reason": reason,
        })

        issue.timeline_events.append({
            "date": report_date,
            "event": "STATUS_TRANSITION",
            "from": old_status.value,
            "to": IssueStatus.RESOLVED.value,
            "reason": reason,
        })

        logger.info(
            "Issue '%s' transitioned: %s → RESOLVED (evidence: '%s')",
            issue.title, old_status.value, event.title
        )

    # ------------------------------------------------------------------
    # Issue Matching (existing logic, preserved)
    # ------------------------------------------------------------------

    def _find_matching_issue(self, event: Event) -> Issue | None:
        """Find an existing active issue that matches the given event.

        Args:
            event: The event to match against existing issues.

        Returns:
            The best matching Issue, or None if no match is found.
        """
        best_match: Issue | None = None
        best_score: float = 0.0
        threshold = config.ISSUE_MATCH_THRESHOLD

        event_norm = normalize_issue_title(event.title)

        for issue in self._issues:
            # Skip resolved/closed issues — they should not accumulate new events
            if issue.status in (IssueStatus.RESOLVED, IssueStatus.CLOSED):
                continue

            issue_norm = issue.normalized_title or normalize_issue_title(issue.title)

            # Check title similarity
            score = title_similarity(event_norm, issue_norm)

            # Shared entities/clients boost
            shared_entities = []
            entities_to_check = [
                "client abc", "client xyz",
                "payment gateway", "paytm", "gateway", "checkout",
                "webhook", "redis", "cors", "csv export", "analytics api",
                "android", "mobile", "font scaling", "composite index",
                "staging database", "android app", "ios app", "app crash",
                "webhook incident", "redis retry", "backend", "dashboard"
            ]

            event_lower = event.title.lower()
            issue_lower = issue.title.lower()

            for ent in entities_to_check:
                if ent in event_lower and ent in issue_lower:
                    shared_entities.append(ent)

            if shared_entities:
                score += 0.35 * len(shared_entities)

            has_client = ("client abc" in event_lower and "client abc" in issue_lower) or \
                         ("client xyz" in event_lower and "client xyz" in issue_lower)
            if has_client:
                score += 0.40

            score = min(score, 1.5)

            if score >= threshold and score > best_score:
                best_score = score
                best_match = issue

        if best_match is not None:
            logger.debug(
                "Matched event '%s' to issue '%s' (score=%.3f)",
                event.title, best_match.title, best_score
            )

        return best_match

    def _update_issue(self, issue: Issue, event: Event, report_date: str) -> None:
        """Update an existing issue with data from a new matching event.

        Args:
            issue: The existing issue to update.
            event: The new event that matched.
            report_date: The date being processed.
        """
        issue.last_seen = event.created_at
        issue.last_updated = datetime.now(timezone.utc)
        issue.occurrence_count += 1

        if not issue.normalized_title:
            issue.normalized_title = normalize_issue_title(issue.title)

        # Append event ID if not already linked
        if event.id not in issue.linked_event_ids:
            issue.linked_event_ids.append(event.id)

        # Merge affected areas
        for area in event.affected_areas:
            if area not in issue.affected_areas:
                issue.affected_areas.append(area)

        # Track severity changes
        issue.severity_history.append({
            "date": report_date,
            "severity": event.severity.value,
        })

        # Escalate issue severity if the new event is more severe
        severity_order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        if severity_order.index(event.severity) > severity_order.index(issue.severity):
            issue.severity = event.severity

        # Update affected team from event participants/areas
        if event.participants and not issue.affected_team:
            issue.affected_team = normalize_name(event.participants[0])

        # Add timeline event
        issue.timeline_events.append({
            "date": report_date,
            "event": "UPDATED",
            "title": event.title,
            "description": event.description,
            "severity": event.severity.value
        })

        logger.debug(
            "Updated issue '%s': occurrence_count=%d, severity=%s",
            issue.title, issue.occurrence_count, issue.severity.value
        )

    def _create_issue(self, event: Event, report_date: str) -> Issue:
        """Create a new Issue from an event that didn't match any existing issues.

        Args:
            event: The unmatched event.
            report_date: The date being processed.

        Returns:
            A new Issue domain object.
        """
        now = datetime.now(timezone.utc)
        issue = Issue(
            id=generate_id("iss", event.title, event.event_type.value),
            title=event.title,
            normalized_title=normalize_issue_title(event.title),
            summary=event.description,
            severity=event.severity,
            status=IssueStatus.OPEN,
            first_seen=event.created_at,
            last_seen=event.created_at,
            occurrence_count=1,
            affected_areas=list(event.affected_areas),
            linked_event_ids=[event.id],
            affected_team=normalize_name(event.participants[0]) if event.participants else None,
            affected_channel=None,
            severity_history=[{
                "date": report_date,
                "severity": event.severity.value,
            }],
            status_history=[{
                "date": report_date,
                "from": "NEW",
                "to": IssueStatus.OPEN.value,
                "reason": f"Created from event: {event.title[:80]}",
            }],
            timeline_events=[{
                "date": report_date,
                "event": "CREATED",
                "title": event.title,
                "description": event.description,
                "severity": event.severity.value
            }],
            last_updated=now,
            days_open=0
        )

        logger.debug("Created new issue: '%s' (severity=%s)", issue.title, issue.severity.value)
        return issue



    # ------------------------------------------------------------------
    # Escalation & Classification
    # ------------------------------------------------------------------

    def _update_all_days_open_and_last_updated(self, report_date: str) -> None:
        """Update last_updated and calculate days_open for all issues."""
        try:
            report_dt = datetime.fromisoformat(report_date).date()
        except ValueError:
            report_dt = datetime.now(timezone.utc).date()

        for issue in self._issues:
            # Set last_updated if None
            if issue.last_updated is None:
                issue.last_updated = issue.last_seen

            # Calculate days_open and handle auto-transition RESOLVED -> CLOSED after 7 days
            if issue.status == IssueStatus.RESOLVED and issue.resolved_at:
                issue.days_open = max(0, (issue.resolved_at.date() - issue.first_seen.date()).days)
                resolved_days = (report_dt - issue.resolved_at.date()).days
                if resolved_days > 7:
                    old_status = issue.status
                    issue.status = IssueStatus.CLOSED
                    issue.last_updated = datetime.now(timezone.utc)
                    reason = "Auto-transition to CLOSED: issue remained RESOLVED for more than 7 days."
                    issue.status_history.append({
                        "date": report_date,
                        "from": old_status.value,
                        "to": IssueStatus.CLOSED.value,
                        "reason": reason,
                    })
                    issue.timeline_events.append({
                        "date": report_date,
                        "event": "STATUS_TRANSITION",
                        "from": old_status.value,
                        "to": IssueStatus.CLOSED.value,
                        "reason": reason,
                    })
                    logger.info("Issue '%s' auto-closed (resolved %d days ago)", issue.title, resolved_days)
            elif issue.status == IssueStatus.CLOSED and issue.resolved_at:
                issue.days_open = max(0, (issue.resolved_at.date() - issue.first_seen.date()).days)
            else:
                issue.days_open = max(0, (report_dt - issue.first_seen.date()).days)

    def _apply_escalation_to_all(self, report_date: str) -> None:
        """Apply escalation logic to all active issues."""
        for issue in self._issues:
            if issue.status in (IssueStatus.OPEN, IssueStatus.MONITORING):
                self._classifier._apply_escalation(issue, report_date)

    def _apply_classification_to_all(self, report_date: str) -> None:
        """Apply founder classification to all issues."""
        for issue in self._issues:
            self._classifier.classify_issue(issue, report_date)

    def _scan_threads_for_resolutions(self, threads: list[Thread], report_date: str) -> None:
        """Scan all thread messages directly for resolution signals and match them to open issues.

        This helps identify resolutions mentioned in chat that didn't generate formal resolution events.
        """
        detector = ResolutionDetector()
        for thread in threads:
            for msg in thread.messages:
                # Run resolution analysis on the raw message text
                conf, matched = detector.analyze_text(msg.text)
                
                # Determine target status
                if conf >= 0.8:
                    target_status = IssueStatus.RESOLVED
                    is_resolution = True
                elif conf >= 0.4:
                    target_status = IssueStatus.MONITORING
                    is_resolution = True
                else:
                    is_resolution = False

                if is_resolution:
                    # Create a temporary Event to reuse the existing resolution matching logic
                    # Set title and description to msg.text to maximize matching potential
                    temp_event = Event(
                        id=f"evt-msg-{msg.id}",
                        title=msg.text,
                        description=msg.text,
                        event_type=EventType.PRODUCTION_INCIDENT,  # fallback event type
                        severity=Severity.LOW,
                        source_thread_id=thread.id,
                        confidence_score=conf,
                        created_at=msg.timestamp
                    )
                    
                    matched_issue = self._find_matching_issue_for_resolution(temp_event)
                    if matched_issue is not None:
                        res_result = ResolutionDetectionResult(
                            is_resolution=True,
                            resolution_confidence=conf,
                            matched_keywords=matched,
                            evidence_message_id=msg.id,
                            evidence_author=msg.sender,
                            evidence_text=msg.text,
                            target_status=target_status
                        )
                        
                        if target_status == IssueStatus.RESOLVED:
                            if matched_issue.status in (IssueStatus.OPEN, IssueStatus.MONITORING):
                                self._transition_to_resolved(matched_issue, temp_event, report_date, res_result)
                        elif target_status == IssueStatus.MONITORING:
                            if matched_issue.status == IssueStatus.OPEN:
                                self._transition_to_monitoring(matched_issue, temp_event, report_date, res_result)

