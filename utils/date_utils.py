"""Utility functions for parsing, formatting, and comparing dates.

Handles the DD-MM-YYYY filename format used by raw data files and
provides date arithmetic helpers for the issue tracker and report generator.
"""

import datetime
import re


def parse_filename_date(filename: str) -> datetime.date:
    """Extract a date from a raw data filename in DD-MM-YYYY format.

    Args:
        filename: The filename (with or without .json extension).

    Returns:
        A datetime.date object.

    Raises:
        ValueError: If the filename does not match the expected DD-MM-YYYY pattern.
    """
    # Strip extension and path
    name = filename.replace(".json", "").split("/")[-1].split("\\")[-1]

    match = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", name)
    if not match:
        raise ValueError(
            f"Filename '{filename}' does not match expected DD-MM-YYYY format."
        )

    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    return datetime.date(year, month, day)


def format_date(date: datetime.date) -> str:
    """Format a date as an ISO 8601 string (YYYY-MM-DD).

    Args:
        date: The date to format.

    Returns:
        A string in YYYY-MM-DD format.
    """
    return date.isoformat()


def format_date_for_filename(date: datetime.date) -> str:
    """Format a date for use in output filenames as YYYY-MM-DD.

    Args:
        date: The date to format.

    Returns:
        A string in YYYY-MM-DD format suitable for filenames.
    """
    return date.isoformat()


def days_between(d1: datetime.date, d2: datetime.date) -> int:
    """Calculate the absolute number of days between two dates.

    Args:
        d1: First date.
        d2: Second date.

    Returns:
        A non-negative integer representing the number of days between the dates.
    """
    return abs((d2 - d1).days)
