"""API Ninjas SEC ingestion (10-K focused) plus filing section extraction."""

from __future__ import annotations

import os
import re
import time
from html import unescape
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from tradingagents.dataflows.api_file_cache import cache_get_json, cache_set_json
from tradingagents.dataflows.config import DataVendorSkipped

SEC_ENDPOINT = "https://api.api-ninjas.com/v1/sec"


def _api_key() -> Optional[str]:
    # Accept both common spellings to reduce env misconfiguration risk.
    return (
        os.getenv("API_NINJA_API_KEY", "").strip()
        or os.getenv("API_NINJAS_API_KEY", "").strip()
        or None
    )


def _fetch_sec_filings(ticker: str, filing: str) -> List[Dict[str, Any]]:
    key = _api_key()
    if not key:
        raise DataVendorSkipped("API_NINJA_API_KEY (or API_NINJAS_API_KEY) not set")
    params = {"ticker": ticker.upper(), "filing": filing}
    headers = {"X-Api-Key": key}
    r = requests.get(SEC_ENDPOINT, params=params, headers=headers, timeout=45)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def get_sec_filing_highlights_ninjas(ticker: str, curr_date: str, filing: str = "10-K") -> str:
    """Return latest SEC filing links/metadata from API Ninjas."""
    try:
        datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError as exc:
        return f"Invalid curr_date for SEC filing lookup: {curr_date} ({exc})"

    filing = (filing or "10-K").upper()
    if filing != "10-K":
        # Plan scope: 10-K only in v1.
        filing = "10-K"

    cache_key = f"ninjas_sec_{ticker.upper()}_{filing}_{curr_date}"
    cached = cache_get_json("api_ninjas", cache_key, ttl_seconds=6 * 3600)
    if cached is None:
        payload = {
            "fetched_at": time.time(),
            "results": _fetch_sec_filings(ticker, filing),
        }
        cache_set_json("api_ninjas", cache_key, payload)
    else:
        payload = cached

    rows = payload.get("results") or []
    source_note = "cached" if cached is not None else "live API"
    lines = [
        f"# SEC Filing Highlights ({filing}) for {ticker.upper()}",
        f"As of trade date: {curr_date}",
        f"Source: API Ninjas SEC ({source_note})",
        "",
    ]
    if not rows:
        lines.append("No filings returned for this ticker/form combination.")
        return "\n".join(lines)

    rows_sorted = sorted(rows, key=lambda r: str(r.get("filing_date", "")), reverse=True)
    latest = rows_sorted[0]
    lines.extend(
        [
            "## Latest filing",
            f"- Ticker: {latest.get('ticker', ticker.upper())}",
            f"- Form: {latest.get('form_type', filing)}",
            f"- Filing date: {latest.get('filing_date', 'N/A')}",
            f"- Filing URL: {latest.get('filing_url', 'N/A')}",
            "",
            "## Additional recent filings",
        ]
    )
    for row in rows_sorted[1:5]:
        lines.append(
            f"- {row.get('filing_date', 'N/A')} | {row.get('form_type', filing)} | {row.get('filing_url', 'N/A')}"
        )
    lines.extend(
        [
            "",
            "## Missing-data notes",
            "- API returns filing links/metadata only; no section text extraction in this tool.",
            "- Use filing URL for deeper manual/secondary parsing when required.",
        ]
    )
    return "\n".join(lines)


def _strip_html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    # Preserve structure before stripping tags so section boundaries survive.
    text = re.sub(r"(?i)</?(p|div|tr|table|section|article|h1|h2|h3|h4|h5|h6|li|br)\b[^>]*>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text


def _extract_item_section(
    text: str,
    start_pat: str,
    end_pats: List[str],
    max_chars: int = 5000,
    min_chars: int = 500,
) -> str:
    """Extract a likely full section body, skipping short TOC-like matches."""
    starts = list(re.finditer(start_pat, text, flags=re.IGNORECASE))
    if not starts:
        return ""

    candidates: List[str] = []
    for s in starts:
        start = s.start()
        end = len(text)
        for pat in end_pats:
            m = re.search(pat, text[start + 1 :], flags=re.IGNORECASE)
            if m:
                end = min(end, start + 1 + m.start())
        snippet = text[start:end].strip()
        if len(snippet) >= min_chars:
            candidates.append(snippet)

    if not candidates:
        # Fallback to last match if all matches are short (better than empty).
        s = starts[-1]
        start = s.start()
        end = len(text)
        for pat in end_pats:
            m = re.search(pat, text[start + 1 :], flags=re.IGNORECASE)
            if m:
                end = min(end, start + 1 + m.start())
        return text[start:end].strip()[:max_chars]

    # Prefer the longest substantial section (usually real body over TOC line).
    best = max(candidates, key=len)
    return best[:max_chars]


def _download_sec_filing_text(url: str) -> str:
    headers = {
        "User-Agent": "TradingAgents/1.0 (research tooling; contact: noreply@example.com)",
        "Accept": "text/html,application/xhtml+xml",
    }
    r = requests.get(url, headers=headers, timeout=60)
    r.raise_for_status()
    return _strip_html_to_text(r.text)


def get_sec_filing_sections_ninjas(ticker: str, curr_date: str) -> str:
    """Fetch latest 10-K URL via API Ninjas, then extract key filing sections from SEC HTML."""
    rows = _fetch_sec_filings(ticker, "10-K")
    if not rows:
        return (
            f"# SEC Filing Sections (10-K) for {ticker.upper()}\n"
            f"As of trade date: {curr_date}\n"
            "No 10-K filing rows returned by API Ninjas."
        )
    rows_sorted = sorted(rows, key=lambda r: str(r.get("filing_date", "")), reverse=True)
    latest = rows_sorted[0]
    filing_url = latest.get("filing_url", "")
    filing_date = latest.get("filing_date", "N/A")
    if not filing_url:
        return (
            f"# SEC Filing Sections (10-K) for {ticker.upper()}\n"
            f"As of trade date: {curr_date}\n"
            "Latest API Ninjas row has no filing_url."
        )

    text = _download_sec_filing_text(filing_url)

    business = _extract_item_section(
        text,
        r"(?m)^\s*item\s*1\.?\s*business\b",
        [r"\bitem\s*1a\.?\s*risk factors\b", r"\bitem\s*2\.?\b"],
        max_chars=3500,
    )
    risks = _extract_item_section(
        text,
        r"(?m)^\s*item\s*1a\.?\s*risk factors\b",
        [r"\bitem\s*1b\.?\b", r"\bitem\s*2\.?\b"],
        max_chars=4000,
    )
    mda = _extract_item_section(
        text,
        r"(?m)^\s*item\s*7\.?\s*management[’']?s?\s+discussion\s+and\s+analysis\b",
        [r"\bitem\s*7a\.?\b", r"\bitem\s*8\.?\b"],
        max_chars=5000,
    )
    financials = _extract_item_section(
        text,
        r"(?m)^\s*item\s*8\.?\s*financial statements\b",
        [r"\bitem\s*9\.?\b"],
        max_chars=5000,
    )
    footnotes = _extract_item_section(
        text,
        r"(?m)^\s*notes?\s+to\s+(consolidated\s+)?financial statements\b",
        [r"\bitem\s*9\.?\b", r"\bsignatures\b"],
        max_chars=4500,
        min_chars=300,
    )

    return "\n".join(
        [
            f"# SEC Filing Sections (10-K) for {ticker.upper()}",
            f"As of trade date: {curr_date}",
            f"Filing date: {filing_date}",
            f"Filing URL: {filing_url}",
            "",
            "## Practical reading order (required)",
            "1) MD&A",
            "2) Financial statements",
            "3) Footnotes",
            "4) Risk Factors",
            "5) Business section (context)",
            "",
            "## MD&A",
            mda or "Section not confidently extracted from filing text.",
            "",
            "## Financial statements",
            financials or "Section not confidently extracted from filing text.",
            "",
            "## Footnotes",
            footnotes or "Section not confidently extracted from filing text.",
            "",
            "## Risk Factors",
            risks or "Section not confidently extracted from filing text.",
            "",
            "## Business",
            business or "Section not confidently extracted from filing text.",
        ]
    )


def get_earnings_transcript_highlights_stub(ticker: str, curr_date: str) -> str:
    """Stub transcript lane so prompts can reason about missing evidence explicitly."""
    return (
        f"# Earnings Transcript Highlights (stub) for {ticker.upper()}\n"
        f"As of trade date: {curr_date}\n"
        "Source: transcript provider not configured\n\n"
        "No transcript ingestion provider is enabled yet.\n"
        "Treat transcript-based claims as unavailable from tools."
    )
