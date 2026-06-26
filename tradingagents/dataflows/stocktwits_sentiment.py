"""StockTwits social-sentiment connector.

The Social Media analyst historically only had `get_news`, so its "sentiment"
was really a news proxy. StockTwits exposes a public per-symbol message stream
where many posts carry an explicit Bullish/Bearish tag, giving a genuine
crowd-sentiment signal.

This is a live endpoint (recent messages only), so in strict historical eval
mode it returns a skip message rather than leaking present-day sentiment into a
point-in-time backtest -- the same pattern used by the CNN Fear & Greed feed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import requests

from tradingagents.dataflows.config import DataVendorSkipped
from tradingagents.dataflows.temporal import is_strict_temporal, skip_live_only_message

STOCKTWITS_URL = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"


def _headers() -> Dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }


def _symbol(ticker: str) -> str:
    # StockTwits uses bare US symbols; drop any exchange suffix (e.g. RY.TO).
    return ticker.strip().upper().split(".")[0]


def get_social_sentiment_stocktwits(ticker: str, curr_date: str) -> str:
    """Aggregate recent StockTwits message sentiment for ``ticker``."""
    try:
        datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError as exc:
        return f"Invalid curr_date for social sentiment: {curr_date} ({exc})"

    if is_strict_temporal():
        return skip_live_only_message(
            "StockTwits social sentiment",
            curr_date,
            "live-only message stream; not available for historical point-in-time eval",
        )

    url = STOCKTWITS_URL.format(symbol=_symbol(ticker))
    try:
        r = requests.get(url, headers=_headers(), timeout=30)
        r.raise_for_status()
        payload: Dict[str, Any] = r.json()
    except Exception as exc:
        raise DataVendorSkipped(f"StockTwits sentiment unavailable: {exc}") from exc

    messages: List[Dict[str, Any]] = payload.get("messages") or []
    if not messages:
        return f"# StockTwits sentiment for {ticker} as of {curr_date}\n- No recent messages found."

    bullish = bearish = neutral = 0
    examples: List[str] = []
    for msg in messages:
        sentiment = ((msg.get("entities") or {}).get("sentiment") or {}).get("basic")
        if sentiment == "Bullish":
            bullish += 1
        elif sentiment == "Bearish":
            bearish += 1
        else:
            neutral += 1
        if len(examples) < 5:
            body = (msg.get("body") or "").replace("\n", " ").strip()
            tag = sentiment or "untagged"
            examples.append(f"  - [{tag}] {body[:160]}")

    total = len(messages)
    tagged = bullish + bearish
    bull_share = (bullish / tagged) if tagged else None
    net = (bullish - bearish) / total if total else 0.0

    lines = [
        f"# StockTwits social sentiment for {ticker} as of {curr_date}",
        f"- Messages sampled: {total}",
        f"- Bullish-tagged: {bullish}",
        f"- Bearish-tagged: {bearish}",
        f"- Untagged/neutral: {neutral}",
        (
            f"- Bullish share of tagged messages: {bull_share:.0%}"
            if bull_share is not None
            else "- Bullish share of tagged messages: n/a (no tagged messages)"
        ),
        f"- Net sentiment (bull-bear)/total: {net:+.2f}",
        "",
        "## Recent message examples",
        *examples,
        "",
        "## How to use",
        "- Crowd-sentiment proxy from retail traders; prone to hype and manipulation.",
        "- Weigh against fundamentals, positioning, and news; flag divergences explicitly.",
    ]
    return "\n".join(lines)
