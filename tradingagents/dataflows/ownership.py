"""Institutional ownership and short-interest connector (Yahoo Finance).

Adds two signals the pipeline previously lacked: who owns the stock
(institutional concentration / fund flows) and how heavily it is shorted
(short ratio, short percent of float). Both are live snapshots from Yahoo, so
strict historical eval mode returns a skip message instead of leaking
present-day ownership into a point-in-time backtest.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import yfinance as yf

from tradingagents.dataflows.config import DataVendorSkipped
from tradingagents.dataflows.temporal import is_strict_temporal, skip_live_only_message


def _fmt_pct(val) -> str:
    try:
        return f"{float(val) * 100:.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def get_ownership_short_interest_yfinance(ticker: str, curr_date: str) -> str:
    """Institutional ownership + short interest snapshot for ``ticker``."""
    try:
        datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError as exc:
        return f"Invalid curr_date for ownership lookup: {curr_date} ({exc})"

    if is_strict_temporal():
        return skip_live_only_message(
            "Institutional ownership & short interest",
            curr_date,
            "Yahoo exposes only a live snapshot; no point-in-time ownership history",
        )

    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
    except Exception as exc:
        raise DataVendorSkipped(f"Yahoo ownership data unavailable: {exc}") from exc

    lines: List[str] = [
        f"# Ownership & short interest for {ticker.upper()} as of {curr_date}",
        "",
        "## Short interest",
        f"- Short ratio (days to cover): {info.get('shortRatio', 'N/A')}",
        f"- Shares short: {info.get('sharesShort', 'N/A')}",
        f"- Short % of float: {_fmt_pct(info.get('shortPercentOfFloat'))}",
        f"- Shares short prior month: {info.get('sharesShortPriorMonth', 'N/A')}",
        "",
        "## Ownership concentration",
        f"- Held by institutions: {_fmt_pct(info.get('heldPercentInstitutions'))}",
        f"- Held by insiders: {_fmt_pct(info.get('heldPercentInsiders'))}",
        f"- Float shares: {info.get('floatShares', 'N/A')}",
    ]

    try:
        inst = tk.institutional_holders
    except Exception:
        inst = None
    if inst is not None and not getattr(inst, "empty", True):
        lines.extend(["", "## Top institutional holders"])
        for _, row in inst.head(8).iterrows():
            holder = row.get("Holder", "N/A")
            shares = row.get("Shares", "N/A")
            pct = row.get("% Out", row.get("pctHeld", ""))
            lines.append(f"- {holder}: {shares} shares ({pct})")

    lines.extend(
        [
            "",
            "## How to use",
            "- High short ratio + improving fundamentals can fuel squeezes; high short ratio + deteriorating",
            "  fundamentals confirms bearish positioning.",
            "- Heavy institutional concentration raises single-holder exit risk.",
        ]
    )
    return "\n".join(lines)
