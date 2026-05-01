"""CNN Fear & Greed Index fetcher."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

import requests

from tradingagents.dataflows.config import DataVendorSkipped

CNN_FG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


def _headers() -> Dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.cnn.com/markets/fear-and-greed",
        "Origin": "https://www.cnn.com",
    }


def get_fear_greed_index_cnn(curr_date: str) -> str:
    """Retrieve CNN Fear & Greed index snapshot and key indicator scores."""
    try:
        datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError as exc:
        return f"Invalid curr_date for Fear & Greed: {curr_date} ({exc})"

    try:
        r = requests.get(CNN_FG_URL, headers=_headers(), timeout=30)
        r.raise_for_status()
        payload: Dict[str, Any] = r.json()
    except Exception as exc:
        raise DataVendorSkipped(f"CNN Fear & Greed unavailable: {exc}") from exc

    fg = payload.get("fear_and_greed") or {}
    score = fg.get("score")
    rating = fg.get("rating", "unknown")
    timestamp = fg.get("timestamp", "N/A")
    prev_close = fg.get("previous_close", "N/A")
    prev_week = fg.get("previous_1_week", "N/A")
    prev_month = fg.get("previous_1_month", "N/A")
    prev_year = fg.get("previous_1_year", "N/A")

    lines = [
        f"# CNN Fear & Greed Index snapshot as of {curr_date}",
        f"- Current score: {score}",
        f"- Current rating: {rating}",
        f"- Timestamp: {timestamp}",
        f"- Previous close: {prev_close}",
        f"- 1 week ago: {prev_week}",
        f"- 1 month ago: {prev_month}",
        f"- 1 year ago: {prev_year}",
        "",
        "## How to use",
        "- Use this as market sentiment context, not as a standalone trading signal.",
        "- Cross-check with trend, macro regime, and company fundamentals before conclusions.",
    ]

    indicator_keys = [
        "market_momentum_sp500",
        "stock_price_strength",
        "stock_price_breadth",
        "put_call_options",
        "market_volatility_vix",
        "safe_haven_demand",
        "junk_bond_demand",
    ]
    present = []
    for key in indicator_keys:
        if key in payload:
            v = payload.get(key) or {}
            present.append(f"- {key}: score={v.get('score', 'N/A')} rating={v.get('rating', 'N/A')}")
    if present:
        lines.extend(["", "## Component indicators", *present])
    return "\n".join(lines)
