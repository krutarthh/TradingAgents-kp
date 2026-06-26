"""Finnhub news and earnings calendar (optional low-cost fallback).

Requires ``FINNHUB_API_KEY``. Used as a failover when Yahoo news/calendar
returns sparse or empty results in live mode.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

import requests

from tradingagents.dataflows.config import DataVendorSkipped
from tradingagents.dataflows.temporal import is_strict_temporal, skip_live_only_message

_BASE = "https://finnhub.io/api/v1"


def _api_key() -> str | None:
    return os.getenv("FINNHUB_API_KEY") or os.getenv("FINNHUB_TOKEN")


def _get_json(path: str, params: Dict[str, Any]) -> Any:
    key = _api_key()
    if not key:
        raise DataVendorSkipped("FINNHUB_API_KEY not set")
    params = {**params, "token": key}
    r = requests.get(f"{_BASE}{path}", params=params, timeout=45)
    if r.status_code in (401, 403):
        raise DataVendorSkipped(f"Finnhub auth failed: {r.status_code}")
    r.raise_for_status()
    return r.json()


def get_news_finnhub(ticker: str, start_date: str, end_date: str) -> str:
    """Company news from Finnhub for the requested date window."""
    if is_strict_temporal():
        return skip_live_only_message(
            "Finnhub company news",
            end_date,
            "Finnhub free tier is live-oriented; use yfinance/AV in strict historical eval",
        )

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as exc:
        return f"Invalid date range for Finnhub news: {exc}"

    try:
        articles = _get_json(
            "/company-news",
            {
                "symbol": ticker.upper(),
                "from": start_dt.strftime("%Y-%m-%d"),
                "to": end_dt.strftime("%Y-%m-%d"),
            },
        )
    except DataVendorSkipped:
        raise
    except requests.RequestException as exc:
        raise DataVendorSkipped(f"Finnhub news request failed: {exc}") from exc

    if not isinstance(articles, list) or not articles:
        raise DataVendorSkipped(f"Finnhub returned no news for {ticker.upper()}")

    lines: List[str] = [
        f"## {ticker.upper()} News (Finnhub), from {start_date} to {end_date}:",
        "",
    ]
    for article in articles[:25]:
        if not isinstance(article, dict):
            continue
        title = article.get("headline") or article.get("title") or "No title"
        summary = article.get("summary") or ""
        source = article.get("source") or "Finnhub"
        url = article.get("url") or ""
        ts = article.get("datetime")
        when = ""
        if ts:
            try:
                when = datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d")
            except (TypeError, ValueError, OSError):
                when = str(ts)
        lines.append(f"### {title} ({source}, {when})")
        if summary:
            lines.append(summary)
        if url:
            lines.append(f"Link: {url}")
        lines.append("")

    if len(lines) <= 2:
        raise DataVendorSkipped(f"Finnhub returned no usable articles for {ticker.upper()}")
    return "\n".join(lines)


def get_earnings_calendar_finnhub(ticker: str, curr_date: str) -> str:
    """Upcoming earnings dates from Finnhub earnings calendar."""
    try:
        datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError as exc:
        return f"Invalid curr_date for Finnhub earnings calendar: {curr_date} ({exc})"

    if is_strict_temporal():
        return skip_live_only_message(
            "Finnhub earnings calendar",
            curr_date,
            "Finnhub calendar is a live snapshot",
        )

    as_of = datetime.strptime(curr_date, "%Y-%m-%d")
    try:
        rows = _get_json(
            "/calendar/earnings",
            {
                "from": as_of.strftime("%Y-%m-%d"),
                "to": (as_of + timedelta(days=120)).strftime("%Y-%m-%d"),
                "symbol": ticker.upper(),
            },
        )
    except DataVendorSkipped:
        raise
    except requests.RequestException as exc:
        raise DataVendorSkipped(f"Finnhub earnings calendar failed: {exc}") from exc

    earnings = rows.get("earningsCalendar") if isinstance(rows, dict) else rows
    if not isinstance(earnings, list):
        earnings = []

    sym = ticker.upper()
    matched = [r for r in earnings if isinstance(r, dict) and r.get("symbol", "").upper() == sym]
    if not matched:
        raise DataVendorSkipped(f"Finnhub has no upcoming earnings row for {sym}")

    lines = [f"# Earnings calendar for {sym} as of {curr_date} (Finnhub)", ""]
    for row in matched[:4]:
        lines.extend(
            [
                f"- Date: {row.get('date', 'N/A')}",
                f"  EPS estimate: {row.get('epsEstimate', 'N/A')}",
                f"  Revenue estimate: {row.get('revenueEstimate', 'N/A')}",
                f"  Quarter: {row.get('quarter', 'N/A')} {row.get('year', '')}".strip(),
                "",
            ]
        )
    lines.extend(
        [
            "## How to use",
            "- Size positions and stops around the next earnings date (event risk).",
        ]
    )
    return "\n".join(lines)
