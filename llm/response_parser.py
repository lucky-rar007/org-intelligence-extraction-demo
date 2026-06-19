"""Utility for parsing and validating raw LLM responses into domain models and schemas."""

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any
import uuid

import pydantic

from domain.enums import EventType, IssueStatus, Severity, IntelligenceType
from domain.models import Event, Issue, IntelligenceFinding
from domain.schemas import ExtractedEvent, FindingCandidate

logger = logging.getLogger(__name__)


class ResponseParseError(Exception):
    """Raised when raw response text cannot be parsed as valid JSON."""
    pass


class ResponseValidationError(Exception):
    """Raised when parsed JSON does not conform to the expected Pydantic schema."""
    pass


class ResponseParser:
    """Parses raw text responses from LLMs into validated Python dicts, schemas, or domain models."""

    def parse_json_response(self, response_text: str) -> dict[str, Any]:
        """Extract JSON from raw LLM text (handling code fences and extra text) and parse into a dictionary.

        Args:
            response_text: The raw text response from the LLM.

        Returns:
            A parsed Python dictionary representation of the JSON.

        Raises:
            ResponseParseError: If JSON parsing fails.
        """
        if not response_text or not response_text.strip():
            logger.error("parsing errors: empty response")
            raise ResponseParseError("LLM response is empty or blank.")

        # Safely isolate the JSON payload by finding the outermost brackets or curly braces.
        start_obj = response_text.find('{')
        end_obj = response_text.rfind('}')
        
        start_arr = response_text.find('[')
        end_arr = response_text.rfind(']')

        # Determine which outer structure to parse
        has_obj = start_obj != -1 and end_obj != -1 and end_obj > start_obj
        has_arr = start_arr != -1 and end_arr != -1 and end_arr > start_arr

        if has_obj and (not has_arr or start_obj < start_arr):
            cleaned_text = response_text[start_obj:end_obj + 1]
        elif has_arr:
            cleaned_text = response_text[start_arr:end_arr + 1]
        else:
            logger.error("malformed json: no outer object or array brackets found")
            raise ResponseParseError("No JSON structure (object or array) found in the response.")

        try:
            parsed = json.loads(cleaned_text)
            logger.info("response parsed successfully")
            return parsed
        except json.JSONDecodeError as e:
            logger.error("malformed json: json decoding failed: %s", str(e))
            logger.error("parsing errors: %s", str(e))
            raise ResponseParseError(f"Failed to parse text as JSON: {e}") from e

    def parse_events(self, response_text: str) -> list[Event]:
        """Parse JSON, validate using Event schemas, and convert to domain Event objects.

        Args:
            response_text: The raw JSON/text response from the LLM.

        Returns:
            A list of Event domain models.

        Raises:
            ResponseParseError: If JSON parsing fails.
            ResponseValidationError: If schema validation fails.
        """
        data = self.parse_json_response(response_text)
        
        # Handle list, nested list, or single object formats
        if isinstance(data, list):
            event_dicts = data
        elif isinstance(data, dict):
            if "events" in data:
                event_dicts = data["events"]
            else:
                event_dicts = [data]
        else:
            logger.error("schema validation failure: root element is not an object or a list")
            raise ResponseValidationError("Expected a JSON object or list for event data.")

        events = []
        for index, item in enumerate(event_dicts):
            try:
                # Align fields from alternative LLM naming (e.g. summary, confidence)
                if isinstance(item, dict):
                    if "summary" in item and "description" not in item:
                        item["description"] = item["summary"]
                    if "confidence" in item and "confidence_score" not in item:
                        item["confidence_score"] = item["confidence"]

                    # Normalize event_type, severity, and status to match enums
                    if "event_type" in item:
                        item["event_type"] = self._normalize_event_type(item["event_type"])
                    if "severity" in item:
                        item["severity"] = self._normalize_severity(item["severity"])
                    if "status" in item:
                        item["status"] = self._normalize_status(item["status"])

                # Validate using ExtractedEvent schema
                ext_event = ExtractedEvent.model_validate(item)


                
                # Convert to domain Event object
                event = Event(
                    id=f"evt-{uuid.uuid4()}",
                    title=ext_event.title,
                    description=ext_event.description,
                    event_type=ext_event.event_type,
                    severity=ext_event.severity,
                    source_thread_id="unknown",
                    participants=ext_event.participants,
                    affected_areas=ext_event.affected_areas,
                    status=ext_event.status,
                    confidence_score=ext_event.confidence_score,
                    created_at=datetime.now(timezone.utc)
                )
                events.append(event)
            except pydantic.ValidationError as e:
                logger.error("schema validation failure: event index %d validation failed: %s", index, str(e))
                raise ResponseValidationError(f"Schema validation failure for event: {e}") from e

        logger.info("schema validation success")
        return events



    def parse_intelligence_finding(self, response_text: str) -> IntelligenceFinding:
        """Parse JSON, validate IntelligenceFinding schema/model, and return the domain object.

        Args:
            response_text: The raw JSON/text response from the LLM.

        Returns:
            An IntelligenceFinding domain model instance.

        Raises:
            ResponseParseError: If JSON parsing fails.
            ResponseValidationError: If validation fails.
        """
        data = self.parse_json_response(response_text)
        
        # Check if it validates against the full domain model directly
        try:
            finding = IntelligenceFinding.model_validate(data)
            logger.info("schema validation success")
            return finding
        except pydantic.ValidationError as e_model:
            # Fallback to validating as FindingCandidate and converting
            try:
                candidate = FindingCandidate.model_validate(data)
                finding = IntelligenceFinding(
                    id=f"fnd-{uuid.uuid4()}",
                    title=candidate.title,
                    summary=candidate.summary,
                    severity=candidate.severity,
                    supporting_event_ids=candidate.supporting_event_ids,
                    recommendation=candidate.recommendation,
                    created_at=datetime.now(timezone.utc)
                )
                logger.info("schema validation success")
                return finding
            except pydantic.ValidationError as e_schema:
                logger.error("schema validation failure: %s", str(e_model))
                raise ResponseValidationError(
                    f"Schema validation failure for IntelligenceFinding: {e_model}. "
                    f"Candidate validation details: {e_schema}"
                ) from e_model



    def _normalize_event_type(self, val: str) -> str:
        """Helper to normalize free-form LLM event type strings to valid EventType values."""
        if not val or not isinstance(val, str):
            return val
        cleaned = val.strip().replace(" ", "_").replace("-", "_").upper()
        valid_types = {e.value for e in EventType}
        if cleaned in valid_types:
            return cleaned

        # Mappings of common variations to valid enums
        synonyms = {
            "CUSTOMER_COMPLAINT": "CLIENT_ESCALATION",
            "CUSTOMER_REQUEST": "CLIENT_REQUEST",
            "PROJECT_RISK": "RISK_INDICATOR",
            "OPERATIONAL_RISK": "RISK_INDICATOR",
            "RISK": "RISK_INDICATOR",
            "DATABASE_ISSUE": "ENVIRONMENT_ISSUE",
            "DEPLOYMENT_FAILURE": "PRODUCTION_INCIDENT",
            "DEPLOYMENT_ISSUE": "ENVIRONMENT_ISSUE",
            "BUILD_FAILURE": "INFRASTRUCTURE_ISSUE",
            "NETWORK_ISSUE": "INFRASTRUCTURE_ISSUE",
            "OUTAGE": "PRODUCTION_INCIDENT",
            "INCIDENT": "PRODUCTION_INCIDENT",
            "BLOCKER": "DELIVERY_BLOCKED",
            "DELAY": "RELEASE_DELAY",
        }
        if cleaned in synonyms:
            return synonyms[cleaned]

        # Keyword mapping fallbacks
        if "DELIVERY_DELAY" in cleaned or "RELEASE_DELAY" in cleaned or "DELAY" in cleaned:
            return "RELEASE_DELAY"
        if "BLOCK" in cleaned:
            return "DELIVERY_BLOCKED"
        if "RISK" in cleaned:
            return "RISK_INDICATOR"
        if "WAIT" in cleaned or "DEPEND" in cleaned:
            return "DEPENDENCY_WAIT"
        if "INCIDENT" in cleaned or "OUTAGE" in cleaned or "FAILURE" in cleaned:
            return "PRODUCTION_INCIDENT"
        if "INFRASTRUCTURE" in cleaned or "NETWORK" in cleaned or "BUILD" in cleaned:
            return "INFRASTRUCTURE_ISSUE"
        if "ENVIRONMENT" in cleaned or "DEPLOY" in cleaned:
            return "ENVIRONMENT_ISSUE"
        if "ESCALAT" in cleaned or "COMPLAINT" in cleaned:
            return "CLIENT_ESCALATION"
        if "REQUEST" in cleaned:
            return "CLIENT_REQUEST"

        for vt in valid_types:
            if vt in cleaned or cleaned == vt:
                return vt
        return val

    def _normalize_severity(self, val: str) -> str:
        """Helper to normalize free-form LLM severity strings to valid Severity values."""
        if not val or not isinstance(val, str):
            return val
        cleaned = val.strip().upper()
        valid_severities = {e.value for e in Severity}
        if cleaned in valid_severities:
            return cleaned
        for vs in valid_severities:
            if vs in cleaned or cleaned in vs:
                return vs
        return val

    def _normalize_status(self, val: str) -> str:
        """Helper to normalize free-form LLM status strings to valid IssueStatus values."""
        if not val or not isinstance(val, str):
            return val
        cleaned = val.strip().upper()
        valid_statuses = {e.value for e in IssueStatus}
        if cleaned in valid_statuses:
            return cleaned
        # Map legacy and common synonyms
        synonyms = {
            "ACTIVE": "OPEN",
            "STALE": "CLOSED",
            "FIXED": "RESOLVED",
            "DONE": "RESOLVED",
            "COMPLETED": "RESOLVED",
            "ARCHIVED": "CLOSED",
        }
        if cleaned in synonyms:
            return synonyms[cleaned]
        for vs in valid_statuses:
            if vs in cleaned or cleaned in vs:
                return vs
        return val
