"""File I/O helper functions.

Provides safe JSON read/write operations and directory creation used
by the storage layer throughout the pipeline.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def ensure_directory(path: Path) -> None:
    """Create a directory and all parent directories if they do not exist.

    Args:
        path: The directory path to create.
    """
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    """Safely load and parse a JSON file.

    Args:
        path: The path to the JSON file.

    Returns:
        The parsed JSON data (dict, list, etc.).

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    logger.debug("Loaded JSON from %s", path)
    return data


def save_json(path: Path, data: Any, indent: int = 2) -> None:
    """Safely write data to a JSON file, creating parent directories as needed.

    Args:
        path: The target file path.
        data: The data to serialize to JSON.
        indent: JSON indentation level for readability.
    """
    ensure_directory(path.parent)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, default=str)

    logger.debug("Saved JSON to %s", path)
