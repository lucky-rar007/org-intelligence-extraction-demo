"""Persists and retrieves extracted events.

Provides JSON-based file storage for events, organized by date.
Supports idempotent writes and date-based retrieval.
"""

import json
import logging
from pathlib import Path

from domain.models import Event
from utils.file_utils import ensure_directory, load_json, save_json
import config

logger = logging.getLogger(__name__)


class EventStore:
    """JSON file-based persistence for extracted Event domain objects."""

    def __init__(self, output_dir: Path = config.EVENTS_OUTPUT_DIR) -> None:
        """Initialize the EventStore.

        Args:
            output_dir: Directory where event JSON files are stored.
        """
        self.output_dir = output_dir
        ensure_directory(self.output_dir)

    def _get_file_path(self, date_str: str) -> Path:
        """Build the file path for events on a given date.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            Path to the events JSON file for that date.
        """
        return self.output_dir / f"{date_str}_events.json"

    def save_events(self, events: list[Event], date_str: str) -> None:
        """Persist a list of events for the given date.

        Args:
            events: List of Event domain objects to save.
            date_str: Date string in YYYY-MM-DD format.
        """
        file_path = self._get_file_path(date_str)
        events_data = [json.loads(e.model_dump_json()) for e in events]
        save_json(file_path, events_data)
        logger.info("Saved %d events for %s to %s", len(events), date_str, file_path)

    def load_events(self, date_str: str) -> list[Event]:
        """Load events for a given date from storage.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            A list of Event domain objects. Returns an empty list if the file does not exist.
        """
        file_path = self._get_file_path(date_str)
        if not file_path.exists():
            logger.debug("No events file found for %s", date_str)
            return []

        try:
            data = load_json(file_path)
            events = [Event.model_validate(item) for item in data]
            logger.info("Loaded %d events for %s", len(events), date_str)
            return events
        except Exception as e:
            logger.error("Failed to load events for %s: %s", date_str, str(e))
            return []

    def events_exist(self, date_str: str) -> bool:
        """Check if events have already been stored for a given date.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            True if an events file exists for the date.
        """
        return self._get_file_path(date_str).exists()
