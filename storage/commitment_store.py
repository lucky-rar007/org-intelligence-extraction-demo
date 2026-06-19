"""Persists and retrieves commitments.

Provides JSON-based file storage for commitments with cross-day persistence.
"""

import json
import logging
from pathlib import Path

from domain.models import Commitment
from utils.file_utils import ensure_directory, load_json, save_json
import config

logger = logging.getLogger(__name__)


class CommitmentStore:
    """JSON file-based persistence for Commitment domain objects."""

    def __init__(self, output_dir: Path = config.ISSUES_OUTPUT_DIR) -> None:
        """Initialize the CommitmentStore.

        Args:
            output_dir: Directory where commitment JSON files are stored.
        """
        self.output_dir = output_dir
        ensure_directory(self.output_dir)
        self._commitments_file = self.output_dir / "commitments.json"

    def save_commitments(self, commitments: list[Commitment]) -> None:
        """Persist the full list of commitments.

        Overwrites the existing commitments file with the current state.

        Args:
            commitments: Complete list of Commitment domain objects to persist.
        """
        commitments_data = [json.loads(c.model_dump_json()) for c in commitments]
        save_json(self._commitments_file, commitments_data)
        logger.info("Saved %d commitments to %s", len(commitments), self._commitments_file)

    def load_commitments(self) -> list[Commitment]:
        """Load all commitments from storage.

        Returns:
            A list of Commitment domain objects. Returns an empty list if no file exists.
        """
        if not self._commitments_file.exists():
            logger.debug("No commitments file found at %s", self._commitments_file)
            return []

        try:
            data = load_json(self._commitments_file)
            commitments = [Commitment.model_validate(item) for item in data]
            logger.info("Loaded %d commitments", len(commitments))
            return commitments
        except Exception as e:
            logger.error("Failed to load commitments: %s", str(e))
            return []
