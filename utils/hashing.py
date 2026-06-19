"""Hashing utilities for deduplication and integrity checks.

Provides deterministic content-based ID generation and text hashing
for deduplication throughout the pipeline.
"""

import hashlib
import uuid


def hash_text(text: str) -> str:
    """Generate a SHA-256 hex digest of the given text.

    Args:
        text: The text to hash.

    Returns:
        A lowercase hex string representing the SHA-256 hash.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate_id(prefix: str, *content_parts: str) -> str:
    """Generate a deterministic, prefixed ID from content parts.

    Creates a reproducible UUID-style identifier by hashing the concatenated
    content parts. The same inputs always produce the same output.

    Args:
        prefix: A short prefix for the ID (e.g., 'evt', 'obs', 'iss', 'fnd').
        *content_parts: One or more strings whose combined hash forms the ID.

    Returns:
        A string in the format '{prefix}-{uuid}' derived from the content hash.
    """
    combined = "|".join(content_parts)
    content_hash = hash_text(combined)
    # Use first 32 hex chars to form a UUID-compatible string
    deterministic_uuid = uuid.UUID(content_hash[:32])
    return f"{prefix}-{deterministic_uuid}"
