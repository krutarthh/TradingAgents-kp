"""Consistent machine-readable headers on string tool responses for triangulation."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple


def infer_symbol_and_as_of(method: str, args: tuple, kwargs: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort ticker and as-of date from route_to_vendor call."""
    kw = dict(kwargs)
    ticker = kw.get("ticker") or kw.get("symbol") or kw.get("tickers")
    if ticker and not isinstance(ticker, str):
        ticker = str(ticker)
    as_of = kw.get("curr_date") or kw.get("end_date") or kw.get("trade_date")
    if as_of and not isinstance(as_of, str):
        as_of = str(as_of)

    if not ticker and args:
        # Many methods take symbol as first positional string
        if method in (
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement",
            "get_insider_transactions",
            "get_analyst_estimates",
            "get_peer_comparables",
            "get_options_implied_move",
            "get_sec_filing_highlights",
            "get_sec_filing_sections",
            "get_earnings_transcript_highlights",
        ):
            if isinstance(args[0], str):
                ticker = args[0]
            if len(args) >= 2 and isinstance(args[1], str):
                as_of = as_of or args[1]
        elif method == "get_stock_data" and len(args) >= 1 and isinstance(args[0], str):
            ticker = args[0]
            if len(args) >= 3 and isinstance(args[2], str):
                as_of = as_of or args[2]
        elif method == "get_indicators" and args and isinstance(args[0], str):
            ticker = args[0]

    if method == "get_macro_regime" and not as_of and args and isinstance(args[0], str):
        as_of = args[0]
    if method == "get_fear_greed_index" and not as_of and args and isinstance(args[0], str):
        as_of = args[0]

    return ticker, as_of


def format_tool_banner(method: str, vendor: str, args: tuple, kwargs: Mapping[str, Any]) -> str:
    sym, as_of = infer_symbol_and_as_of(method, args, kwargs)
    parts = [f"[tool={method}]", f"[vendor={vendor}]"]
    if sym:
        parts.append(f"[symbol={sym}]")
    if as_of:
        parts.append(f"[as_of={as_of}]")
    return " ".join(parts)


def prefix_string_body(method: str, vendor: str, body: str, args: tuple, kwargs: Mapping[str, Any]) -> str:
    if body is None:
        return format_tool_banner(method, vendor, args, kwargs) + "\n(no data)"
    banner = format_tool_banner(method, vendor, args, kwargs)
    text = body if isinstance(body, str) else str(body)
    if text.lstrip().startswith("[tool="):
        return text
    return f"{banner}\n{text}"
