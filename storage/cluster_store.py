"""Persists and retrieves issue clusters.

Provides JSON-based file storage for issue clusters with cross-day persistence.
"""

import json
import logging
from pathlib import Path

from domain.models import IssueCluster
from utils.file_utils import ensure_directory, load_json, save_json
import config

logger = logging.getLogger(__name__)


class ClusterStore:
    """JSON file-based persistence for IssueCluster domain objects."""

    def __init__(self, output_dir: Path | None = None) -> None:
        """Initialize the ClusterStore.

        Args:
            output_dir: Directory where cluster JSON files are stored. Defaults to config.CLUSTERS_OUTPUT_DIR.
        """
        self.output_dir = output_dir or config.CLUSTERS_OUTPUT_DIR
        ensure_directory(self.output_dir)
        self._clusters_file = self.output_dir / "clusters.json"

    def save_clusters(self, clusters: list[IssueCluster]) -> None:
        """Persist the master list of issue clusters.

        Overwrites the master clusters file with the current state.

        Args:
            clusters: Complete list of IssueCluster domain objects to persist.
        """
        clusters_data = [json.loads(c.model_dump_json()) for c in clusters]
        save_json(self._clusters_file, clusters_data)
        logger.info("Saved %d issue clusters to master store: %s", len(clusters), self._clusters_file)

    def save_daily_snapshot(self, clusters: list[IssueCluster], report_date: str) -> None:
        """Save a daily snapshot of the clusters for historical tracking and audit trails.

        Args:
            clusters: Complete list of IssueCluster domain objects to persist.
            report_date: The report date in YYYY-MM-DD format.
        """
        snapshot_file = self.output_dir / f"{report_date}_clusters.json"
        clusters_data = [json.loads(c.model_dump_json()) for c in clusters]
        save_json(snapshot_file, clusters_data)
        logger.info("Saved daily cluster snapshot to %s", snapshot_file)

    def load_clusters(self) -> list[IssueCluster]:
        """Load all issue clusters from the master storage file.

        Returns:
            A list of IssueCluster domain objects. Returns an empty list if no file exists.
        """
        if not self._clusters_file.exists():
            logger.debug("No clusters file found at %s", self._clusters_file)
            return []

        try:
            data = load_json(self._clusters_file)
            clusters = [IssueCluster.model_validate(item) for item in data]
            logger.info("Loaded %d issue clusters", len(clusters))
            return clusters
        except Exception as e:
            logger.error("Failed to load issue clusters: %s", str(e))
            return []
