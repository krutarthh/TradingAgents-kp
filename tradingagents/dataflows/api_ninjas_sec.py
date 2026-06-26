"""API Ninjas SEC ingestion (10-K / 10-Q / 8-K) plus filing section extraction."""

from __future__ import annotations

import os
import re
import time
from html import unescape
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from tradingagents.dataflows.api_file_cache import cache_get_json, cache_set_json
from tradingagents.dataflows.config import DataVendorSkipped
from tradingagents.dataflows.temporal import filter_rows_on_or_before

SEC_ENDPOINT = "https://api.api-ninjas.com/v1/sec"

# Supported filing forms. 10-K (annual) is the default; 10-Q (quarterly) and
# 8-K (material events) extend timeliness beyond the annual report.
SUPPORTED_FORMS = ("10-K", "10-Q", "8-K")

# API Ninjas SEC uses the primary EDGAR ticker; some user-facing symbols 400.
_SEC_TICKER_ALIASES: Dict[str, Tuple[str, ...]] = {
    "GOOG": ("GOOGL",),
    "FB": ("META",),
}


def _sec_ticker_candidates(ticker: str) -> List[str]:
    """Ordered ticker symbols to try against the API Ninjas SEC endpoint."""
    raw = (ticker or "").strip().upper()
    if not raw:
        return []
    out: List[str] = []
    for sym in _SEC_TICKER_ALIASES.get(raw, ()) + (raw,):
        if sym and sym not in out:
            out.append(sym)
    # US listings with exchange suffix (e.g. RY.TO): try bare symbol as fallback.
    if "." in raw:
        base = raw.split(".", 1)[0]
        if base and base not in out:
            out.append(base)
    return out


def _normalize_form(filing: Optional[str]) -> str:
    form = (filing or "10-K").upper().strip()
    return form if form in SUPPORTED_FORMS else "10-K"


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

    filing = _normalize_form(filing)
    headers = {"X-Api-Key": key}
    candidates = _sec_ticker_candidates(ticker)
    last_error: Optional[BaseException] = None

    for sym in candidates:
        params = {"ticker": sym, "filing": filing}
        try:
            r = requests.get(SEC_ENDPOINT, params=params, headers=headers, timeout=45)
            if r.status_code in (400, 404):
                last_error = requests.HTTPError(
                    f"{r.status_code} for {SEC_ENDPOINT}?ticker={sym}&filing={filing}",
                    response=r,
                )
                continue
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else []
        except requests.HTTPError as exc:
            last_error = exc
            status = exc.response.status_code if exc.response is not None else None
            if status in (400, 404):
                continue
            raise DataVendorSkipped(f"API Ninjas SEC request failed: {exc}") from exc
        except requests.RequestException as exc:
            raise DataVendorSkipped(f"API Ninjas SEC request failed: {exc}") from exc

    tried = ", ".join(candidates) or ticker.upper()
    raise DataVendorSkipped(
        f"API Ninjas SEC: no filings for {ticker.upper()} (form {filing}); tried: {tried}"
    ) from last_error


def get_sec_filing_highlights_ninjas(ticker: str, curr_date: str, filing: str = "10-K") -> str:
    """Return latest SEC filing links/metadata from API Ninjas."""
    try:
        datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError as exc:
        return f"Invalid curr_date for SEC filing lookup: {curr_date} ({exc})"

    filing = _normalize_form(filing)

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
    rows = filter_rows_on_or_before(rows, curr_date, date_field="filing_date")
    source_note = "cached" if cached is not None else "live API"
    lines = [
        f"# SEC Filing Highlights ({filing}) for {ticker.upper()}",
        f"As of trade date: {curr_date}",
        f"Source: API Ninjas SEC ({source_note})",
        "",
    ]
    if not rows:
        lines.append("No filings on or before trade date for this ticker/form combination.")
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


def _sections_10k(text: str) -> List[tuple]:
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
    return [
        ("MD&A", mda),
        ("Financial statements", financials),
        ("Footnotes", footnotes),
        ("Risk Factors", risks),
        ("Business", business),
    ]


def _sections_10q(text: str) -> List[tuple]:
    # 10-Q: Part I Item 1 financials, Item 2 MD&A, Item 3 market risk; Part II
    # Item 1A risk factors (updates only).
    financials = _extract_item_section(
        text,
        r"(?m)^\s*item\s*1\.?\s*financial statements\b",
        [r"\bitem\s*2\.?\s*management", r"\bitem\s*3\.?\b"],
        max_chars=4500,
        min_chars=300,
    )
    mda = _extract_item_section(
        text,
        r"(?m)^\s*item\s*2\.?\s*management[’']?s?\s+discussion\s+and\s+analysis\b",
        [r"\bitem\s*3\.?\b", r"\bitem\s*4\.?\b"],
        max_chars=5000,
    )
    risks = _extract_item_section(
        text,
        r"(?m)^\s*item\s*1a\.?\s*risk factors\b",
        [r"\bitem\s*2\.?\b", r"\bsignatures\b"],
        max_chars=3500,
        min_chars=200,
    )
    return [
        ("MD&A (quarterly)", mda),
        ("Financial statements (quarterly)", financials),
        ("Risk Factor updates", risks),
    ]


def _sections_8k(text: str) -> List[tuple]:
    # 8-K events are short and item-coded; surface the cleaned body (it is
    # already truncated upstream) rather than chasing every numbered item.
    body = text.strip()[:6000]
    return [("Reported events (8-K body excerpt)", body)]


def get_sec_filing_sections_ninjas(ticker: str, curr_date: str, filing: str = "10-K") -> str:
    """Fetch latest filing URL via API Ninjas, then extract key sections from SEC HTML.

    Supports 10-K (annual), 10-Q (quarterly) and 8-K (material events).
    """
    form = _normalize_form(filing)
    rows = filter_rows_on_or_before(
        _fetch_sec_filings(ticker, form), curr_date, date_field="filing_date"
    )
    if not rows:
        return (
            f"# SEC Filing Sections ({form}) for {ticker.upper()}\n"
            f"As of trade date: {curr_date}\n"
            f"No {form} filing rows on or before trade date returned by API Ninjas."
        )
    rows_sorted = sorted(rows, key=lambda r: str(r.get("filing_date", "")), reverse=True)
    latest = rows_sorted[0]
    filing_url = latest.get("filing_url", "")
    filing_date = latest.get("filing_date", "N/A")
    if not filing_url:
        return (
            f"# SEC Filing Sections ({form}) for {ticker.upper()}\n"
            f"As of trade date: {curr_date}\n"
            "Latest API Ninjas row has no filing_url."
        )

    text = _download_sec_filing_text(filing_url)
    if form == "10-Q":
        sections = _sections_10q(text)
        reading_order = ["1) MD&A (quarterly)", "2) Financial statements", "3) Risk Factor updates"]
    elif form == "8-K":
        sections = _sections_8k(text)
        reading_order = ["1) Reported events"]
    else:
        sections = _sections_10k(text)
        reading_order = [
            "1) MD&A",
            "2) Financial statements",
            "3) Footnotes",
            "4) Risk Factors",
            "5) Business section (context)",
        ]

    out = [
        f"# SEC Filing Sections ({form}) for {ticker.upper()}",
        f"As of trade date: {curr_date}",
        f"Filing date: {filing_date}",
        f"Filing URL: {filing_url}",
        "",
        "## Practical reading order (required)",
        *reading_order,
        "",
    ]
    for title, body in sections:
        out.append(f"## {title}")
        out.append(body or "Section not confidently extracted from filing text.")
        out.append("")
    return "\n".join(out).rstrip()


def get_earnings_transcript_highlights_stub(ticker: str, curr_date: str) -> str:
    """Stub transcript lane so prompts can reason about missing evidence explicitly."""
    return (
        f"# Earnings Transcript Highlights (stub) for {ticker.upper()}\n"
        f"As of trade date: {curr_date}\n"
        "Source: transcript provider not configured\n\n"
        "No transcript ingestion provider is enabled yet.\n"
        "Treat transcript-based claims as unavailable from tools."
    )
