"""SEC EDGAR filing metadata and section extraction (free, no API key).

Uses official SEC data APIs:
- https://www.sec.gov/files/company_tickers.json
- https://data.sec.gov/submissions/CIK##########.json

Section HTML download + parsing reuses helpers from ``api_ninjas_sec``.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Tuple

import requests

from tradingagents.dataflows.api_file_cache import cache_get_json, cache_set_json
from tradingagents.dataflows.config import DataVendorSkipped
from tradingagents.dataflows.api_ninjas_sec import (
    _download_sec_filing_text,
    _normalize_form,
    _sections_10k,
    _sections_10q,
    _sections_8k,
)
from tradingagents.dataflows.temporal import filter_rows_on_or_before

_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Same alias map as API Ninjas — EDGAR tickers file may list only primary symbol.
_TICKER_ALIASES: Dict[str, Tuple[str, ...]] = {
    "GOOG": ("GOOGL",),
    "FB": ("META",),
}


def _user_agent() -> str:
    return (
        os.getenv("SEC_EDGAR_USER_AGENT", "").strip()
        or "TradingAgents/1.0 (research tooling; contact: noreply@example.com)"
    )


def _headers() -> Dict[str, str]:
    return {
        "User-Agent": _user_agent(),
        "Accept": "application/json",
    }


def _get_json(url: str) -> Any:
    r = requests.get(url, headers=_headers(), timeout=45)
    r.raise_for_status()
    return r.json()


def _ticker_candidates(ticker: str) -> List[str]:
    raw = (ticker or "").strip().upper()
    out: List[str] = []
    for sym in _TICKER_ALIASES.get(raw, ()) + (raw,):
        if sym and sym not in out:
            out.append(sym)
    if "." in raw:
        base = raw.split(".", 1)[0]
        if base and base not in out:
            out.append(base)
    return out or [raw]


def _load_ticker_map() -> Dict[str, int]:
    cached = cache_get_json("sec_edgar", "company_tickers", ttl_seconds=7 * 24 * 3600)
    if cached is None:
        data = _get_json(_TICKERS_URL)
        mapping: Dict[str, int] = {}
        for entry in data.values():
            if not isinstance(entry, dict):
                continue
            sym = str(entry.get("ticker", "")).upper()
            cik = entry.get("cik_str")
            if sym and cik is not None:
                mapping[sym] = int(cik)
        cache_set_json("sec_edgar", "company_tickers", mapping)
        return mapping
    return cached


def _resolve_cik(ticker: str) -> int:
    mapping = _load_ticker_map()
    for sym in _ticker_candidates(ticker):
        if sym in mapping:
            return mapping[sym]
    raise DataVendorSkipped(f"SEC EDGAR: no CIK found for ticker {ticker.upper()}")


def _form_matches(requested: str, reported: str) -> bool:
    reported = (reported or "").upper()
    requested = requested.upper()
    if reported == requested:
        return True
    # Include amendments e.g. 10-K/A when user asked for 10-K.
    return reported.startswith(requested + "/")


def _row_from_submission(
    ticker: str,
    cik: int,
    form: str,
    filing_date: str,
    accession: str,
    primary_doc: str,
) -> Dict[str, Any]:
    acc_path = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_path}/{primary_doc}"
    return {
        "ticker": ticker.upper(),
        "form_type": form,
        "filing_date": filing_date,
        "filing_url": url,
    }


def _iter_submission_chunks(cik: int) -> Iterator[Dict[str, Any]]:
    main_url = f"{_SUBMISSIONS_BASE}/CIK{int(cik):010d}.json"
    main = _get_json(main_url)
    recent = (main.get("filings") or {}).get("recent")
    if recent:
        yield recent
    for meta in (main.get("filings") or {}).get("files") or []:
        name = meta.get("name") if isinstance(meta, dict) else None
        if not name:
            continue
        yield _get_json(f"{_SUBMISSIONS_BASE}/{name}")


def _fetch_edgar_filings(ticker: str, filing: str) -> List[Dict[str, Any]]:
    filing = _normalize_form(filing)
    sym = _ticker_candidates(ticker)[0]
    cik = _resolve_cik(ticker)
    cache_key = f"edgar_filings_{cik}_{filing}"
    cached = cache_get_json("sec_edgar", cache_key, ttl_seconds=6 * 3600)
    if cached is not None:
        return cached.get("results") or []

    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    try:
        for chunk in _iter_submission_chunks(cik):
            if not chunk:
                continue
            forms = chunk.get("form") or []
            dates = chunk.get("filingDate") or []
            accessions = chunk.get("accessionNumber") or []
            docs = chunk.get("primaryDocument") or []
            for form, fdate, acc, doc in zip(forms, dates, accessions, docs):
                if not _form_matches(filing, str(form)):
                    continue
                key = f"{acc}|{doc}"
                if key in seen:
                    continue
                seen.add(key)
                rows.append(_row_from_submission(sym, cik, str(form), str(fdate), str(acc), str(doc)))
    except requests.RequestException as exc:
        raise DataVendorSkipped(f"SEC EDGAR request failed: {exc}") from exc

    payload = {"fetched_at": time.time(), "results": rows}
    cache_set_json("sec_edgar", cache_key, payload)
    return rows


def get_sec_filing_highlights_edgar(ticker: str, curr_date: str, filing: str = "10-K") -> str:
    """Return latest SEC filing links/metadata from SEC EDGAR."""
    try:
        datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError as exc:
        return f"Invalid curr_date for SEC filing lookup: {curr_date} ({exc})"

    filing = _normalize_form(filing)
    rows = filter_rows_on_or_before(
        _fetch_edgar_filings(ticker, filing), curr_date, date_field="filing_date"
    )
    lines = [
        f"# SEC Filing Highlights ({filing}) for {ticker.upper()}",
        f"As of trade date: {curr_date}",
        "Source: SEC EDGAR (official submissions API)",
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
            "- Metadata from EDGAR submissions; use `get_sec_filing_sections` for parsed section text.",
        ]
    )
    return "\n".join(lines)


def get_sec_filing_sections_edgar(ticker: str, curr_date: str, filing: str = "10-K") -> str:
    """Fetch latest filing URL via EDGAR, then extract key sections from SEC HTML."""
    form = _normalize_form(filing)
    rows = filter_rows_on_or_before(
        _fetch_edgar_filings(ticker, form), curr_date, date_field="filing_date"
    )
    if not rows:
        return (
            f"# SEC Filing Sections ({form}) for {ticker.upper()}\n"
            f"As of trade date: {curr_date}\n"
            f"No {form} filing rows on or before trade date returned by SEC EDGAR."
        )

    rows_sorted = sorted(rows, key=lambda r: str(r.get("filing_date", "")), reverse=True)
    latest = rows_sorted[0]
    filing_url = latest.get("filing_url", "")
    filing_date = latest.get("filing_date", "N/A")
    if not filing_url:
        return (
            f"# SEC Filing Sections ({form}) for {ticker.upper()}\n"
            f"As of trade date: {curr_date}\n"
            "Latest EDGAR row has no filing_url."
        )

    try:
        text = _download_sec_filing_text(filing_url)
    except requests.RequestException as exc:
        raise DataVendorSkipped(f"SEC EDGAR filing download failed: {exc}") from exc

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
        f"Source: SEC EDGAR",
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
