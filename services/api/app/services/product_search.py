"""Helpers for the product full-text search feature."""
from __future__ import annotations
import re

# Allow letters, digits, dashes, underscores. Keep unicode letters via re.UNICODE.
_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)


def make_tsquery(raw: str | None) -> str:
    """Convert a free-text query into a `to_tsquery('simple', ...)` argument.

    Returns "" when the input has no usable tokens — the caller should treat
    this as 'no search filter applied'.
    """
    if not raw:
        return ""
    tokens = _TOKEN_RE.findall(raw)
    tokens = [t.lower() for t in tokens if t]
    if not tokens:
        return ""
    # Prefix match each token, AND them all
    return " & ".join(f"{t}:*" for t in tokens)
