"""Persists and retrieves tracked issues.

Provides JSON-based file storage for issues with cross-day persistence.
Includes idempotency safeguards via processed date tracking to prevent
duplicate issue updates when the pipeline is run multiple times.
"""

import json
import logging
from pathlib import Path

from domain.models import Issue
from utils.file_utils import ensure_directory, load_json, save_json
import config

logger = logging.getLogger(__name__)


class IssueStore:
    """JSON file-based persistence for Issue domain objects with idempotency tracking."""

    def __init__(self, output_dir: Path = config.ISSUES_OUTPUT_DIR) -> None:
        """Initialize the IssueStore.

        Args:
            output_dir: Directory where issue and tracking JSON files are stored.
        """
        self.output_dir = output_dir
        ensure_directory(self.output_dir)
        self._issues_file = self.output_dir / "issues.json"
        self._processed_dates_file = self.output_dir / "processed_dates.json"

    def save_issues(self, issues: list[Issue]) -> None:
        """Persist the full list of tracked issues.

        Overwrites the existing issues file with the current state.

        Args:
            issues: Complete list of Issue domain objects to persist.
        """
        import os
        issues_data = [json.loads(i.model_dump_json()) for i in issues]
        tmp_file = self._issues_file.with_name(self._issues_file.name + ".tmp")
        save_json(tmp_file, issues_data)
        os.replace(tmp_file, self._issues_file)
        logger.info("Saved %d issues to %s", len(issues), self._issues_file)

    def load_issues(self) -> list[Issue]:
        """Load all tracked issues from storage.

        Returns:
            A list of Issue domain objects. Returns an empty list if no file exists.
        """
        if not self._issues_file.exists():
            logger.debug("No issues file found at %s", self._issues_file)
            return []

        try:
            data = load_json(self._issues_file)
            issues = [Issue.model_validate(item) for item in data]
            logger.info("Loaded %d issues", len(issues))
            return issues
        except Exception as e:
            logger.error("Failed to load issues: %s", str(e))
            return []

    def get_processed_dates(self) -> set[str]:
        """Retrieve the set of dates that have already been processed for issue tracking.

        Returns:
            A set of date strings (YYYY-MM-DD) that have been processed.
        """
        if not self._processed_dates_file.exists():
            return set()

        try:
            data = load_json(self._processed_dates_file)
            return set(data)
        except Exception as e:
            logger.error("Failed to load processed dates: %s", str(e))
            return set()

    def mark_date_processed(self, date_str: str) -> None:
        """Record a date as having been processed for issue tracking.

        Args:
            date_str: Date string in YYYY-MM-DD format.
        """
        processed = self.get_processed_dates()
        processed.add(date_str)
        save_json(self._processed_dates_file, sorted(list(processed)))
        logger.info("Marked date %s as processed for issue tracking", date_str)

    def is_date_processed(self, date_str: str) -> bool:
        """Check if a date has already been processed for issue tracking.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            True if the date has been processed.
        """
        return date_str in self.get_processed_dates()
