"""Resolution detection layer for operational events and conversation threads.

Determines whether an event/message indicates that an issue is resolved, in progress (monitoring),
or remains open. Produces confidence scores and extracts matched keywords.
"""

import re
from typing import List, Optional, Tuple
from domain.models import Event, Thread, Message
from domain.enums import IssueStatus
from pydantic import BaseModel


class ResolutionDetectionResult(BaseModel):
    """Result of the resolution detection analysis."""
    is_resolution: bool
    resolution_confidence: float
    matched_keywords: List[str]
    evidence_message_id: Optional[str] = None
    evidence_author: Optional[str] = None
    evidence_text: Optional[str] = None
    target_status: IssueStatus


class ResolutionDetector:
    """Detects issue resolutions from event fields and thread messages."""

    def __init__(self) -> None:
        # Strong indicators of resolution
        self.strong_keywords = [
            "deployed successfully",
            "completed successfully",
            "merged and deployed",
            "confirmed fixed",
            "refund completed",
            "refunds completed",
            "resolved",
            "fixed",
            "working now",
            "verified",
            "closed",
            "completed",
            "issue gone",
            "issues gone",
            "gone now",
            "looks good",
            "confirmed fix",
            "healthy now",
            "restored",
            "recovered",
            "unblocked",
            "deployed to production"
        ]

        # Contextual resolution statements
        self.contextual_statements = [
            "staging looks healthy now",
            "retry issue disappeared",
            "customer confirmed fix",
            "verified on android",
            "pagination issue gone",
            "all support tickets closed",
            "build is passing",
            "production stable",
            "connection pool normal now",
            "looks healthy now",
            "looks good now",
            "working as expected"
        ]

        # Indicators that a fix is deployed/in progress but not yet fully verified
        self.monitoring_keywords = [
            "monitoring now",
            "green now",
            "monitoring production",
            "under observation",
            "canary",
            "waiting for verification",
            "testing in progress",
            "ready for validation",
            "patch deployed",
            "fix merged",
            "deployed to staging",
            "hotfix merged",
            "fix in progress",
            "awaiting confirmation",
            "hotfix release",
            "release to production",
            "monitoring",
            "on its way",
            "deployed"
        ]

        # Weak or uncertain language patterns
        self.weak_keywords = [
            "might be fixed",
            "should be okay",
            "let's see",
            "probably resolved",
            "probably fixed",
            "might be",
            "should be",
            "let's check",
            "could be",
            "hopefully",
            "looks okay",
            "may be"
        ]

    def _has_unnegated_match(self, text: str, keyword: str) -> bool:
        """Checks if the keyword matches and is not preceded by negation words in a 20-char window."""
        idx = 0
        while True:
            idx = text.find(keyword, idx)
            if idx == -1:
                return False
            # Check preceding 20 chars for negation words
            window = text[max(0, idx - 20):idx]
            if any(neg in window for neg in ["not ", "didn't ", "failed to "]):
                idx += 1
                continue
            return True

    def analyze_text(self, text: str) -> Tuple[float, List[str]]:
        """Analyze a string of text to determine if it indicates a resolution.

        Returns:
            Tuple of (confidence_score, list_of_matched_keywords).
        """
        if not text:
            return 0.1, []

        text_lower = text.lower()
        matched_keywords = []

        # Check weak keywords first to see if any are present
        has_weak = False
        for wk in self.weak_keywords:
            if wk in text_lower:
                has_weak = True
                matched_keywords.append(wk)

        # Check contextual statements
        has_contextual = False
        for cs in self.contextual_statements:
            if self._has_unnegated_match(text_lower, cs):
                has_contextual = True
                matched_keywords.append(cs)

        # Check strong keywords
        strong_matches = []
        for sk in self.strong_keywords:
            if self._has_unnegated_match(text_lower, sk):
                strong_matches.append(sk)

        # Minimum message length gate: texts under 8 words require 2+ strong keyword matches
        words = text.split()
        if len(words) < 8 and len(strong_matches) < 2:
            strong_matches = []

        has_strong = False
        if strong_matches:
            has_strong = True
            for sk in strong_matches:
                if sk not in matched_keywords:
                    matched_keywords.append(sk)

        # Check monitoring keywords
        has_monitoring = False
        for mk in self.monitoring_keywords:
            if self._has_unnegated_match(text_lower, mk):
                has_monitoring = True
                if mk not in matched_keywords:
                    matched_keywords.append(mk)

        # Determine confidence score based on matches
        if (has_strong or has_contextual) and not has_monitoring:
            if has_weak:
                # Downgrade to Medium confidence because of weak/uncertain language
                return 0.5, matched_keywords
            else:
                return 0.9, matched_keywords
        elif has_monitoring or (has_strong and has_monitoring):
            # Prioritize MONITORING if monitoring indicators are present
            # Unless there's a super strong resolution indicator present
            super_strong_words = ["resolved", "fixed", "verified", "confirmed", "completed", "closed", "unblocked", "success"]
            has_super_strong = any(ss in text_lower for ss in super_strong_words)
            if has_super_strong and not has_weak:
                return 0.9, matched_keywords
            else:
                return 0.6, matched_keywords
        elif has_strong or has_contextual:
            # Fallback when strong/contextual matches but weak is present
            if has_weak:
                return 0.5, matched_keywords
            else:
                return 0.9, matched_keywords
        else:
            return 0.1, []

    def detect_resolution(self, event: Event, thread: Optional[Thread] = None) -> ResolutionDetectionResult:
        """Detect if an event or its source thread indicates an issue resolution.

        Args:
            event: The event being analyzed.
            thread: The optional source thread containing messages.

        Returns:
            A ResolutionDetectionResult mapping to resolved, monitoring, or open.
        """
        # Start by analyzing the event title and description
        event_text = f"{event.title} {event.description}"
        best_conf, best_matched = self.analyze_text(event_text)

        evidence_msg_id = event.id
        evidence_author = "System (extracted event)"
        evidence_text = event.description

        # If we have a source thread with messages, analyze them for better details
        if thread and thread.messages:
            for msg in thread.messages:
                conf, matched = self.analyze_text(msg.text)
                # We select the message that yields the highest confidence match
                if conf > best_conf:
                    best_conf = conf
                    best_matched = matched
                    evidence_msg_id = msg.id
                    evidence_author = msg.sender
                    evidence_text = msg.text

        # Determine target status and whether it's classified as a resolution
        if best_conf >= 0.8:
            target_status = IssueStatus.RESOLVED
            is_resolution = True
        elif best_conf >= 0.4:
            target_status = IssueStatus.MONITORING
            is_resolution = True
        else:
            target_status = IssueStatus.OPEN
            is_resolution = False

        return ResolutionDetectionResult(
            is_resolution=is_resolution,
            resolution_confidence=best_conf,
            matched_keywords=best_matched,
            evidence_message_id=evidence_msg_id,
            evidence_author=evidence_author,
            evidence_text=evidence_text,
            target_status=target_status
        )
