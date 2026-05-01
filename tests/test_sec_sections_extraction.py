"""Unit tests for SEC section extraction heuristics."""

import pytest

from tradingagents.dataflows.api_ninjas_sec import _extract_item_section


@pytest.mark.unit
def test_extract_item_section_skips_short_toc_and_prefers_body():
    toc = "Item 7. Management's Discussion and Analysis 31\n"
    body = (
        "Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations\n"
        + ("This is real MD&A body text. " * 120)
        + "\nItem 8. Financial Statements and Supplementary Data\n"
    )
    text = toc + body
    out = _extract_item_section(
        text,
        r"(?m)^\s*item\s*7\.?\s*management[’']?s?\s+discussion\s+and\s+analysis\b",
        [r"\bitem\s*8\.?\b"],
        min_chars=300,
    )
    assert "real MD&A body text" in out
    assert len(out) > 300

