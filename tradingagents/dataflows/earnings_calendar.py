"""Earnings calendar connector (Yahoo Finance).

Surfaces upcoming and recent earnings dates so agents can reason about catalyst
timing (the prompts already ask for a catalyst calendar). Yahoo exposes only a
live snapshot of scheduled dates, so strict historical eval mode skips it.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import yfinance as yf

from tradingagents.dataflows.config import DataVendorSkipped
from tradingagents.dataflows.temporal import is_strict_temporal, skip_live_only_message


def get_earnings_calendar_yfinance(ticker: str, curr_date: str) -> str:
    """Upcoming and recent earnings dates for ``ticker``."""
    try:
        datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError as exc:
        return f"Invalid curr_date for earnings calendar: {curr_date} ({exc})"

    if is_strict_temporal():
        return skip_live_only_message(
            "Earnings calendar",
            curr_date,
            "Yahoo exposes only a live snapshot of scheduled dates; no historical calendar",
        )

    try:
        tk = yf.Ticker(ticker)
    except Exception as exc:
        raise DataVendorSkipped(f"Yahoo earnings calendar unavailable: {exc}") from exc

    lines: List[str] = [f"# Earnings calendar for {ticker.upper()} as of {curr_date}", ""]

    try:
        cal = tk.calendar
    except Exception:
        cal = None
    if isinstance(cal, dict) and cal:
        ed = cal.get("Earnings Date")
        if ed:
            lines.append(f"- Next earnings date: {ed}")
        if cal.get("Earnings Average") is not None:
            lines.append(f"- EPS estimate (avg): {cal.get('Earnings Average')}")
        if cal.get("Revenue Average") is not None:
            lines.append(f"- Revenue estimate (avg): {cal.get('Revenue Average')}")

    try:
        dates = tk.get_earnings_dates(limit=8)
    except Exception:
        dates = None
    if dates is not None and not getattr(dates, "empty", True):
        lines.extend(["", "## Recent / upcoming reported quarters"])
        for idx, row in dates.head(8).iterrows():
            eps_est = row.get("EPS Estimate", "")
            eps_act = row.get("Reported EPS", "")
            surprise = row.get("Surprise(%)", "")
            lines.append(f"- {idx.date()}: est={eps_est} actual={eps_act} surprise={surprise}")

    if len(lines) <= 2:
        lines.append("- No earnings calendar data available.")

    lines.extend(
        [
            "",
            "## How to use",
            "- Position sizing and stop placement should account for the next earnings date (event risk).",
            "- Recent surprise history hints at guidance credibility and reaction asymmetry.",
        ]
    )
    return "\n".join(lines)
