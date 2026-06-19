"""Persists and retrieves Observation domain objects.

Provides JSON-based file storage for observations, organized by date.
Supports cross-day accumulation for pattern detection and aggregation.
Observations persist separately from events and are never deleted.
"""

import json
import logging
from pathlib import Path

from domain.models import Observation
from utils.file_utils import ensure_directory, load_json, save_json
import config

logger = logging.getLogger(__name__)


class ObservationStore:
    """JSON file-based persistence for Observation domain objects."""

    def __init__(self, output_dir: Path = config.OBSERVATIONS_OUTPUT_DIR) -> None:
        """Initialize the ObservationStore.

        Args:
            output_dir: Directory where observation JSON files are stored.
        """
        self.output_dir = output_dir
        ensure_directory(self.output_dir)

    def _get_file_path(self, date_str: str) -> Path:
        """Build the file path for observations on a given date.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            Path to the observations JSON file for that date.
        """
        return self.output_dir / f"{date_str}_observations.json"

    def save_observations(self, observations: list[Observation], date_str: str) -> None:
        """Persist a list of observations for the given date.

        Args:
            observations: List of Observation domain objects to save.
            date_str: Date string in YYYY-MM-DD format.
        """
        file_path = self._get_file_path(date_str)
        observations_data = [json.loads(o.model_dump_json()) for o in observations]
        save_json(file_path, observations_data)
        logger.info(
            "Saved %d observations for %s to %s",
            len(observations), date_str, file_path
        )

    def load_observations(self, date_str: str) -> list[Observation]:
        """Load observations for a given date from storage.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            A list of Observation domain objects. Returns an empty list if the file does not exist.
        """
        file_path = self._get_file_path(date_str)
        if not file_path.exists():
            logger.debug("No observations file found for %s", date_str)
            return []

        try:
            data = load_json(file_path)
            observations = [Observation.model_validate(item) for item in data]
            logger.info("Loaded %d observations for %s", len(observations), date_str)
            return observations
        except Exception as e:
            logger.error("Failed to load observations for %s: %s", date_str, str(e))
            return []

    def load_all_observations(self) -> list[Observation]:
        """Load all observations across all dates for cross-day aggregation.

        Returns:
            A merged list of all Observation domain objects from every stored date.
        """
        all_observations: list[Observation] = []
        if not self.output_dir.exists():
            return all_observations

        for file_path in sorted(self.output_dir.glob("*_observations.json")):
            try:
                data = load_json(file_path)
                observations = [Observation.model_validate(item) for item in data]
                all_observations.extend(observations)
            except Exception as e:
                logger.error("Failed to load observations from %s: %s", file_path, str(e))
                continue

        logger.info("Loaded %d total observations across all dates", len(all_observations))
        return all_observations

    def observations_exist(self, date_str: str) -> bool:
        """Check if observations have already been stored for a given date.

        Args:
            date_str: Date string in YYYY-MM-DD format.

        Returns:
            True if an observations file exists for the date.
        """
        return self._get_file_path(date_str).exists()
