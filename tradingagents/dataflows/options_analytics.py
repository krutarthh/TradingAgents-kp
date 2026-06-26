"""Options analytics connector (Yahoo Finance option chains).

Goes beyond the single ATM straddle "implied move" estimate: aggregates the
nearest expiries into a put/call open-interest ratio and an approximate ATM
implied volatility, which are useful tactical positioning and risk signals.

Option chains from Yahoo are live snapshots (no historical chains), so strict
historical eval mode returns a skip message.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import yfinance as yf

from tradingagents.dataflows.config import DataVendorSkipped
from tradingagents.dataflows.temporal import is_strict_temporal, skip_live_only_message


def _spot(tk: yf.Ticker) -> Optional[float]:
    try:
        hist = tk.history(period="5d")
        if hist is not None and not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    try:
        return float((tk.info or {}).get("regularMarketPrice"))
    except (TypeError, ValueError):
        return None


def get_options_analytics_yfinance(ticker: str, curr_date: str, max_expiries: int = 3) -> str:
    """Put/call OI ratio and approximate ATM implied volatility for ``ticker``."""
    try:
        datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError as exc:
        return f"Invalid curr_date for options analytics: {curr_date} ({exc})"

    if is_strict_temporal():
        return skip_live_only_message(
            "Options analytics (put/call, IV)",
            curr_date,
            "Yahoo provides only live option chains; no historical chains for point-in-time eval",
        )

    try:
        tk = yf.Ticker(ticker)
        expiries = list(tk.options or [])
    except Exception as exc:
        raise DataVendorSkipped(f"Yahoo options data unavailable: {exc}") from exc

    if not expiries:
        return f"# Options analytics for {ticker.upper()} as of {curr_date}\n- No listed options found."

    spot = _spot(tk)
    total_call_oi = 0.0
    total_put_oi = 0.0
    atm_ivs: List[float] = []

    for expiry in expiries[:max_expiries]:
        try:
            chain = tk.option_chain(expiry)
        except Exception:
            continue
        calls = chain.calls
        puts = chain.puts
        if calls is not None and not calls.empty:
            total_call_oi += float(calls["openInterest"].fillna(0).sum())
        if puts is not None and not puts.empty:
            total_put_oi += float(puts["openInterest"].fillna(0).sum())
        if spot and calls is not None and not calls.empty:
            calls = calls.copy()
            calls["dist"] = (calls["strike"] - spot).abs()
            atm = calls.nsmallest(1, "dist")
            if not atm.empty:
                iv = atm.iloc[0].get("impliedVolatility")
                if iv and iv == iv:  # not NaN
                    atm_ivs.append(float(iv))

    pc_ratio = (total_put_oi / total_call_oi) if total_call_oi else None
    avg_iv = (sum(atm_ivs) / len(atm_ivs)) if atm_ivs else None

    lines = [
        f"# Options analytics for {ticker.upper()} as of {curr_date}",
        f"- Spot (approx): {spot if spot is not None else 'N/A'}",
        f"- Expiries analyzed: {min(len(expiries), max_expiries)} of {len(expiries)}",
        f"- Total call open interest: {int(total_call_oi)}",
        f"- Total put open interest: {int(total_put_oi)}",
        (
            f"- Put/Call OI ratio: {pc_ratio:.2f}"
            if pc_ratio is not None
            else "- Put/Call OI ratio: n/a"
        ),
        (
            f"- Approx ATM implied volatility: {avg_iv:.1%}"
            if avg_iv is not None
            else "- Approx ATM implied volatility: n/a"
        ),
        "",
        "## How to use",
        "- Put/Call > 1 leans defensive/bearish positioning; < 0.7 leans complacent/bullish.",
        "- Elevated ATM IV signals expected volatility (often around catalysts/earnings).",
    ]
    return "\n".join(lines)
