import datetime
import pytest
from unittest.mock import MagicMock

from domain.models import Thread, Message, Event, Issue
from domain.enums import Severity, IssueStatus
from pipeline.event_extractor import EventExtractor
from pipeline.commitment_extractor import CommitmentExtractor
from pipeline.clustering import ClusteringEngine
from llm.response_parser import ResponseParseError, ResponseValidationError


class MockLLMClient:
    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0

    def generate(self, prompt: str) -> str:
        if self.call_count < len(self.responses):
            res = self.responses[self.call_count]
            self.call_count += 1
            return res
        return ""


def test_event_extractor_retry_success():
    # Attempt 1: malformed JSON (ResponseParseError)
    # Attempt 2: valid JSON but missing/wrong enum fields (ResponseValidationError)
    # Attempt 3: perfect JSON
    responses = [
        "not a json",
        '{"events": [{"title": "DB Outage", "description": "Crash", "event_type": "INVALID_TYPE", "severity": "MEDIUM", "status": "OPEN", "confidence_score": 0.9}]}',
        '{"events": [{"title": "DB Outage", "description": "Crash", "event_type": "PRODUCTION_INCIDENT", "severity": "MEDIUM", "status": "OPEN", "confidence_score": 0.9}]}'
    ]
    client = MockLLMClient(responses)
    extractor = EventExtractor(llm_client=client)

    thread = Thread(
        id="t-1",
        date=datetime.date(2026, 6, 19),
        participants=["Alice", "Bob"],
        messages=[
            Message(id="m-1", sender="Alice", text="Database is down!", timestamp=datetime.datetime.now(datetime.timezone.utc))
        ]
    )

    events = extractor.extract_from_thread(thread)
    assert len(events) == 1
    assert events[0].title == "DB Outage"
    assert events[0].event_type.value == "PRODUCTION_INCIDENT"
    assert client.call_count == 3  # Took 3 attempts


def test_event_extractor_retry_failure():
    # All 3 attempts return malformed JSON
    responses = [
        "malformed 1",
        "malformed 2",
        "malformed 3"
    ]
    client = MockLLMClient(responses)
    extractor = EventExtractor(llm_client=client)

    thread = Thread(
        id="t-2",
        date=datetime.date(2026, 6, 19),
        participants=["Alice"],
        messages=[
            Message(id="m-2", sender="Alice", text="Hi", timestamp=datetime.datetime.now(datetime.timezone.utc))
        ]
    )

    events = extractor.extract_from_thread(thread)
    assert events == []
    assert client.call_count == 3  # Exhausted all attempts


def test_commitment_extractor_retry_success():
    # Attempt 1: not a list, but a dict (ResponseValidationError)
    # Attempt 2: valid list of commitments
    responses = [
        '{"error": "something"}',
        '[{"owner": "Siddharth Rao", "description": "Fix DB connection issue", "due_date": "2026-06-25", "context": "Alice requested it"}]'
    ]
    client = MockLLMClient(responses)
    extractor = CommitmentExtractor(llm_client=client)

    messages = [
        Message(id="m-3", sender="Siddharth Rao", text="I will fix DB connection issue by next week", timestamp=datetime.datetime.now(datetime.timezone.utc))
    ]

    commitments = extractor.extract_commitments(messages, "2026-06-19")
    assert len(commitments) == 1
    assert commitments[0].owner == "Siddharth"
    assert commitments[0].description == "Fix DB connection issue"
    assert client.call_count == 2


def test_commitment_extractor_retry_failure():
    responses = [
        '{"invalid": "format"}',
        '{"invalid": "format"}',
        '{"invalid": "format"}'
    ]
    client = MockLLMClient(responses)
    extractor = CommitmentExtractor(llm_client=client)

    messages = [
        Message(id="m-4", sender="Siddharth Rao", text="I will do it", timestamp=datetime.datetime.now(datetime.timezone.utc))
    ]

    commitments = extractor.extract_commitments(messages, "2026-06-19")
    assert commitments == []
    assert client.call_count == 3


def test_clustering_discovery_retry_success():
    # Attempt 1: not a dict, but a list (ResponseValidationError)
    # Attempt 2: valid new cluster proposal dict
    responses = [
        '["not", "a", "dict"]',
        '{"create_new_cluster": true, "confidence": 0.9, "cluster_name": "Auth Outages", "parent_cluster": "infrastructure_risk", "risk_type": "QUALITY_RISK", "description": "Auth errors", "recommended_action": "Review auth configs", "keywords": ["auth", "login"]}'
    ]
    client = MockLLMClient(responses)

    # Mock cluster_registry and store
    registry_mock = MagicMock()
    registry_mock.load_registry.return_value = []
    registry_mock.load_candidates.return_value = []

    store_mock = MagicMock()
    store_mock.load_clusters.return_value = []

    engine = ClusteringEngine(cluster_store=store_mock, cluster_registry=registry_mock, llm_client=client)

    now = datetime.datetime.now(datetime.timezone.utc)
    issue = Issue(
        id="iss-99",
        title="Auth service is slow",
        summary="login page timed out",
        severity=Severity.HIGH,
        status=IssueStatus.OPEN,
        first_seen=now,
        last_seen=now,
        occurrence_count=1
    )

    clusters = engine.cluster_issues([issue], report_date="2026-06-19")
    # Verified that candidate was added
    registry_mock.add_candidate.assert_called_once()
    assert client.call_count == 2
