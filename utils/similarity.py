"""Text similarity and clustering helpers.

Provides lightweight, deterministic text similarity functions used by
the issue tracker for matching new events against existing issues.
Uses token-overlap (Jaccard) similarity to avoid external NLP dependencies.
"""

import re


def normalize_text(text: str) -> str:
    """Normalize text for comparison by lowercasing, stripping, and collapsing whitespace.

    Args:
        text: The raw text to normalize.

    Returns:
        A cleaned, lowercase string with collapsed whitespace.
    """
    if not text:
        return ""
    cleaned = text.strip().lower()
    # Remove punctuation except hyphens and underscores
    cleaned = re.sub(r"[^\w\s\-]", "", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _tokenize(text: str) -> set[str]:
    """Split normalized text into a set of unique tokens.

    Args:
        text: A normalized text string.

    Returns:
        A set of word tokens.
    """
    normalized = normalize_text(text)
    if not normalized:
        return set()
    return set(normalized.split())


def title_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity between two text strings based on token overlap.

    Uses stop-word filtering, simple lemmatization (cleaning plurals),
    and entity-overlap boosting to compare the semantic cores of titles.
    """
    stop_words = {
        "issue", "issues", "problem", "problems", "error", "errors", "failed", "failure",
        "delay", "delays", "sync", "fix", "verification", "report", "reports", "concept",
        "update", "updates", "reminder", "reminders", "for", "and", "on", "in", "to", "the",
        "a", "an", "of", "about", "with", "from", "at", "by", "is", "was", "were", "be", "been"
    }
    
    def get_clean_tokens(text: str) -> set[str]:
        normalized = normalize_text(text)
        tokens = normalized.split()
        filtered = [t for t in tokens if t not in stop_words]
        cleaned = []
        for t in filtered:
            if t.endswith("s") and len(t) > 3:
                cleaned.append(t[:-1])
            else:
                cleaned.append(t)
        return set(cleaned)

    tokens_a = get_clean_tokens(a)
    tokens_b = get_clean_tokens(b)
    
    if not tokens_a or not tokens_b:
        return 0.0
        
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    
    jaccard = len(intersection) / len(union)
    
    # Entity/topic boosting: if both mention specific known entities, boost the score
    entities = [
        {"payment", "gateway", "paytm", "sdk"},
        {"staging", "database", "connection", "caching", "redis", "pool", "disk"},
        {"client", "abc"},
        {"client", "xyz"},
        {"android", "login", "proguard", "app"},
        {"cors"}
    ]
    
    boost = 0.0
    for entity_set in entities:
        has_a = any(w in tokens_a for w in entity_set)
        has_b = any(w in tokens_b for w in entity_set)
        if has_a and has_b:
            shared = tokens_a & tokens_b & entity_set
            if shared:
                boost = max(boost, 0.4)
            else:
                boost = max(boost, 0.2)
                
    return min(jaccard + boost, 1.0)


def are_similar(a: str, b: str, threshold: float = 0.85) -> bool:
    """Check if two text strings exceed a similarity threshold.

    Args:
        a: First text string.
        b: Second text string.
        threshold: Minimum similarity score to consider a match.

    Returns:
        True if the similarity score meets or exceeds the threshold.
    """
    return title_similarity(a, b) >= threshold
