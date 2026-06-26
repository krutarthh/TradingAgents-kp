"""Shared 5-tier rating vocabulary and a deterministic heuristic parser.

The same five-tier scale (Buy, Overweight, Hold, Underweight, Sell) is used by:
- The Research Manager (investment plan recommendation)
- The Portfolio Manager (final position decision)
- The signal processor (rating extracted for downstream consumers)
- The memory log (rating tag stored alongside each decision entry)

Centralising it here avoids drift between those call sites.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple


# Canonical, ordered 5-tier scale (most bullish to most bearish).
RATINGS_5_TIER: Tuple[str, ...] = (
    "Buy", "Overweight", "Hold", "Underweight", "Sell",
)

_RATING_SET = {r.lower() for r in RATINGS_5_TIER}

# Ordinal conviction score for each tier (most bullish positive, most bearish
# negative). Shared by the runtime signal extractor and the eval metrics so the
# two never drift.
RATING_SCORE = {
    "buy": 2,
    "overweight": 1,
    "hold": 0,
    "underweight": -1,
    "sell": -2,
}

# Matches "Rating: X" / "rating - X" / "Rating: **X**" — tolerates markdown
# bold wrappers and either a colon or hyphen separator.
_RATING_LABEL_RE = re.compile(r"rating.*?[:\-][\s*]*(\w+)", re.IGNORECASE)


def parse_rating_with_status(text: str) -> Tuple[Optional[str], bool]:
    """Extract a 5-tier rating and report whether one was actually found.

    Returns ``(rating, found)``. When no rating word appears, returns
    ``(None, False)`` so callers can flag the parse failure explicitly instead
    of silently treating a missing rating as a (false) neutral Hold.
    """
    for line in text.splitlines():
        m = _RATING_LABEL_RE.search(line)
        if m and m.group(1).lower() in _RATING_SET:
            return m.group(1).capitalize(), True

    for line in text.splitlines():
        for word in line.lower().split():
            clean = word.strip("*:.,")
            if clean in _RATING_SET:
                return clean.capitalize(), True

    return None, False


def parse_rating(text: str, default: str = "Hold") -> str:
    """Heuristically extract a 5-tier rating from prose text.

    Two-pass strategy:
    1. Look for an explicit "Rating: X" label (tolerant of markdown bold).
    2. Fall back to the first 5-tier rating word found anywhere in the text.

    Returns a Title-cased rating string, or ``default`` if no rating word appears.
    For callers that need to distinguish "found Hold" from "found nothing", use
    :func:`parse_rating_with_status` instead.
    """
    rating, found = parse_rating_with_status(text)
    return rating if found else default


def rating_bucket(rating: Optional[str]) -> str:
    """Map a 5-tier rating to bullish / bearish / neutral."""
    r = (rating or "").strip().lower()
    if r in ("buy", "overweight"):
        return "bullish"
    if r in ("sell", "underweight"):
        return "bearish"
    return "neutral"
