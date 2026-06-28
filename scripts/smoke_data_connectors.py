#!/usr/bin/env python3
"""Smoke-test key data connectors for a live ticker."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

TICKER = "AAPL"
DATE = "2026-06-08"
START = "2026-05-25"


def _head(text: str, n: int = 280) -> str:
    t = (text or "").strip().replace("\n", " ")
    return t[:n] + ("..." if len(t) > n else "")


def _run(name: str, fn) -> dict:
    try:
        out = fn()
        body = out if isinstance(out, str) else str(out)
        ok = body and "Error" not in body[:120] and "not set" not in body.lower()[:200]
        skip = "[vendor=" in body and ("skipped" in body.lower() or "unavailable" in body.lower())
        status = "skip" if skip else ("ok" if ok else "weak")
        return {"name": name, "status": status, "preview": _head(body)}
    except Exception as exc:
        return {"name": name, "status": "fail", "preview": str(exc)[:200]}


def main() -> None:
    from tradingagents.dataflows import interface

    tests = [
        ("get_stock_data (yfinance)", lambda: interface.route_to_vendor("get_stock_data", TICKER, START, DATE)),
        ("get_indicators rsi", lambda: interface.route_to_vendor("get_indicators", TICKER, "rsi", DATE, 30)),
        ("get_fundamentals", lambda: interface.route_to_vendor("get_fundamentals", TICKER, DATE)),
        ("get_sec_filing_highlights", lambda: interface.route_to_vendor("get_sec_filing_highlights", TICKER, DATE, "10-K")),
        ("get_earnings_transcript_highlights", lambda: interface.route_to_vendor("get_earnings_transcript_highlights", TICKER, DATE)),
        ("get_analyst_estimates", lambda: interface.route_to_vendor("get_analyst_estimates", TICKER, DATE)),
        ("get_peer_comparables", lambda: interface.route_to_vendor("get_peer_comparables", TICKER, DATE)),
        ("get_macro_regime", lambda: interface.route_to_vendor("get_macro_regime", DATE)),
        ("get_news", lambda: interface.route_to_vendor("get_news", TICKER, START, DATE)),
        ("get_social_sentiment", lambda: interface.route_to_vendor("get_social_sentiment", TICKER, DATE)),
        ("get_fear_greed_index", lambda: interface.route_to_vendor("get_fear_greed_index", DATE)),
        ("get_ownership_short_interest", lambda: interface.route_to_vendor("get_ownership_short_interest", TICKER, DATE)),
        ("get_earnings_calendar", lambda: interface.route_to_vendor("get_earnings_calendar", TICKER, DATE)),
        ("get_options_analytics", lambda: interface.route_to_vendor("get_options_analytics", TICKER, DATE)),
        ("get_options_implied_move", lambda: interface.route_to_vendor("get_options_implied_move", TICKER, DATE)),
    ]

    print(f"Smoke test: {TICKER} as of {DATE}\n")
    counts = {"ok": 0, "skip": 0, "weak": 0, "fail": 0}
    for t in tests:
        r = _run(*t)
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        icon = {"ok": "OK", "skip": "SKIP", "weak": "WEAK", "fail": "FAIL"}[r["status"]]
        print(f"[{icon}] {r['name']}")
        print(f"      {r['preview']}\n")

    print("Summary:", counts)


if __name__ == "__main__":
    main()
