"""Persists and retrieves generated reports.

Provides JSON-based file storage for founder reports with one report per day.
Reports are stored as structured JSON designed to power a dashboard.
"""

import json
import logging
from pathlib import Path

from domain.models import FounderReport
from utils.file_utils import ensure_directory, load_json, save_json
import config

logger = logging.getLogger(__name__)


class ReportStore:
    """JSON file-based persistence for FounderReport domain objects."""

    def __init__(self, output_dir: Path = config.REPORTS_OUTPUT_DIR) -> None:
        """Initialize the ReportStore.

        Args:
            output_dir: Directory where report JSON files are stored.
        """
        self.output_dir = output_dir
        ensure_directory(self.output_dir)

    def _get_file_path(self, date_str: str) -> Path:
        """Build the file path for a report on a given date.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            Path to the report JSON file for that date.
        """
        return self.output_dir / f"{date_str}_founder_report.json"

    def save_report(self, report: FounderReport, date_str: str) -> None:
        """Persist a founder report for the given date.

        Args:
            report: The FounderReport domain object to save.
            date_str: Date string in YYYY-MM-DD format.
        """
        file_path = self._get_file_path(date_str)
        report_data = json.loads(report.model_dump_json())
        save_json(file_path, report_data)
        logger.info("Saved founder report for %s to %s", date_str, file_path)

    def load_report(self, date_str: str) -> FounderReport | None:
        """Load a founder report for a given date from storage.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            A FounderReport domain object, or None if no report exists for the date.
        """
        file_path = self._get_file_path(date_str)
        if not file_path.exists():
            logger.debug("No report file found for %s", date_str)
            return None

        try:
            data = load_json(file_path)
            report = FounderReport.model_validate(data)
            logger.info("Loaded report for %s", date_str)
            return report
        except Exception as e:
            logger.error("Failed to load report for %s: %s", date_str, str(e))
            return None

    def report_exists(self, date_str: str) -> bool:
        """Check if a report has already been stored for a given date.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            True if a report file exists for the date.
        """
        return self._get_file_path(date_str).exists()
