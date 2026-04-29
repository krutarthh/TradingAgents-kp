"""Forward-looking yfinance data helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

from .stockstats_utils import yf_retry


SECTOR_ETF_MAP: Dict[str, str] = {
    "technology": "XLK",
    "healthcare": "XLV",
    "financial services": "XLF",
    "financial": "XLF",
    "consumer cyclical": "XLY",
    "consumer defensive": "XLP",
    "industrials": "XLI",
    "energy": "XLE",
    "utilities": "XLU",
    "real estate": "XLRE",
    "communication services": "XLC",
    "materials": "XLB",
}

SECTOR_PEERS: Dict[str, List[str]] = {
    "technology": ["MSFT", "AAPL", "NVDA", "AMZN", "GOOGL", "META", "ORCL", "ADBE"],
    "healthcare": ["LLY", "JNJ", "PFE", "UNH", "MRK", "ABBV", "TMO", "AMGN"],
    "financial services": ["JPM", "BAC", "GS", "MS", "WFC", "BLK", "SCHW", "C"],
    "financial": ["JPM", "BAC", "GS", "MS", "WFC", "BLK", "SCHW", "C"],
    "consumer cyclical": ["TSLA", "AMZN", "HD", "MCD", "NKE", "SBUX", "LOW", "BKNG"],
    "consumer defensive": ["PG", "KO", "PEP", "WMT", "COST", "PM", "MO", "CL"],
    "industrials": ["GE", "CAT", "BA", "RTX", "DE", "UNP", "HON", "LMT"],
    "energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO"],
    "utilities": ["NEE", "DUK", "SO", "AEP", "EXC", "SRE", "XEL", "D"],
    "real estate": ["PLD", "AMT", "EQIX", "O", "PSA", "SPG", "WELL", "CCI"],
    "communication services": ["GOOGL", "META", "NFLX", "TMUS", "VZ", "T", "DIS", "CMCSA"],
    "materials": ["LIN", "APD", "NEM", "FCX", "ECL", "SHW", "DD", "MLM"],
}


def _to_datetime(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


def _history_return(symbol: str, end_dt: datetime, months: int) -> Optional[float]:
    start_dt = end_dt - timedelta(days=months * 35)
    data = yf_retry(
        lambda: yf.Ticker(symbol).history(
            start=start_dt.strftime("%Y-%m-%d"),
            end=(end_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
        )
    )
    if data is None or data.empty or len(data["Close"]) < 2:
        return None
    start_price = float(data["Close"].iloc[0])
    end_price = float(data["Close"].iloc[-1])
    if start_price == 0:
        return None
    return (end_price - start_price) / start_price


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def _safe_df_to_csv(df: Optional[pd.DataFrame], title: str) -> str:
    if df is None or df.empty:
        return f"## {title}\nNo data available.\n"
    return f"## {title}\n{df.head(12).to_csv(index=True)}\n"


def get_analyst_estimates_yfinance(ticker: str) -> str:
    """Fetch forward-looking analyst and estimate datasets for a ticker."""
    try:
        symbol = ticker.upper()
        tk = yf.Ticker(symbol)
        info = yf_retry(lambda: tk.info) or {}

        blocks = [
            f"# Analyst and Forward Estimates for {symbol}",
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Snapshot",
            f"Current price: {info.get('currentPrice', 'N/A')}",
            f"Target mean price: {info.get('targetMeanPrice', 'N/A')}",
            f"Target high price: {info.get('targetHighPrice', 'N/A')}",
            f"Target low price: {info.get('targetLowPrice', 'N/A')}",
            f"Number of analyst opinions: {info.get('numberOfAnalystOpinions', 'N/A')}",
            f"Recommendation mean: {info.get('recommendationMean', 'N/A')}",
            f"Recommendation key: {info.get('recommendationKey', 'N/A')}",
            "",
            _safe_df_to_csv(yf_retry(lambda: tk.recommendations), "Recommendations History"),
            _safe_df_to_csv(yf_retry(lambda: tk.recommendations_summary), "Recommendations Summary"),
            _safe_df_to_csv(yf_retry(lambda: tk.earnings_estimate), "Earnings Estimate"),
            _safe_df_to_csv(yf_retry(lambda: tk.revenue_estimate), "Revenue Estimate"),
            _safe_df_to_csv(yf_retry(lambda: tk.earnings_history), "Earnings History"),
            _safe_df_to_csv(yf_retry(lambda: tk.growth_estimates), "Growth Estimates"),
        ]
        return "\n".join(blocks)
    except Exception as exc:
        return f"Error fetching analyst estimates for {ticker}: {exc}"


def get_peer_comparables_yfinance(ticker: str, curr_date: str) -> str:
    """Build peer and sector-relative snapshot."""
    try:
        symbol = ticker.upper()
        as_of = _to_datetime(curr_date)
        tk = yf.Ticker(symbol)
        info = yf_retry(lambda: tk.info) or {}
        sector = (info.get("sector") or "").strip()
        sector_key = sector.lower()

        etf = SECTOR_ETF_MAP.get(sector_key, "SPY")
        peer_candidates = SECTOR_PEERS.get(sector_key, ["AAPL", "MSFT", "GOOGL", "AMZN", "META"])
        peers = [p for p in peer_candidates if p != symbol][:5]

        target_1m = _history_return(symbol, as_of, 1)
        target_3m = _history_return(symbol, as_of, 3)
        target_12m = _history_return(symbol, as_of, 12)
        spy_12m = _history_return("SPY", as_of, 12)
        etf_12m = _history_return(etf, as_of, 12)

        rows: List[Tuple[str, Optional[float], Optional[float], Optional[float], Optional[int]]] = []
        for peer in peers:
            peer_tk = yf.Ticker(peer)
            peer_info = yf_retry(lambda p=peer_tk: p.info) or {}
            rows.append(
                (
                    peer,
                    _history_return(peer, as_of, 1),
                    _history_return(peer, as_of, 3),
                    _history_return(peer, as_of, 12),
                    peer_info.get("marketCap"),
                )
            )

        lines = [
            f"# Peer Comparables for {symbol}",
            f"# As of trade date: {curr_date}",
            f"Sector: {sector or 'Unknown'}",
            f"Mapped sector ETF: {etf}",
            "",
            "## Target Relative Returns",
            f"{symbol} 1M: {_fmt_pct(target_1m)}",
            f"{symbol} 3M: {_fmt_pct(target_3m)}",
            f"{symbol} 12M: {_fmt_pct(target_12m)}",
            f"{etf} 12M: {_fmt_pct(etf_12m)}",
            f"SPY 12M: {_fmt_pct(spy_12m)}",
            f"{symbol} vs ETF 12M alpha: {_fmt_pct(None if target_12m is None or etf_12m is None else target_12m - etf_12m)}",
            f"{symbol} vs SPY 12M alpha: {_fmt_pct(None if target_12m is None or spy_12m is None else target_12m - spy_12m)}",
            "",
            "## Peer Return Grid (1M/3M/12M)",
        ]

        for peer, r1m, r3m, r12m, mcap in rows:
            lines.append(
                f"- {peer}: 1M={_fmt_pct(r1m)}, 3M={_fmt_pct(r3m)}, 12M={_fmt_pct(r12m)}, market_cap={mcap if mcap is not None else 'N/A'}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"Error fetching peer comparables for {ticker}: {exc}"


def get_macro_regime_yfinance(curr_date: str) -> str:
    """Summarize macro regime using liquid proxy instruments."""
    try:
        as_of = _to_datetime(curr_date)
        proxies = {
            "VIX": "^VIX",
            "DXY": "DX-Y.NYB",
            "US10Y": "^TNX",
            "WTI_OIL": "CL=F",
            "GOLD": "GC=F",
            "HYG": "HYG",
            "LQD": "LQD",
        }

        changes: Dict[str, Optional[float]] = {}
        levels: Dict[str, Optional[float]] = {}
        for name, symbol in proxies.items():
            ret_1m = _history_return(symbol, as_of, 1)
            changes[name] = ret_1m
            hist = yf_retry(
                lambda s=symbol: yf.Ticker(s).history(
                    start=(as_of - timedelta(days=14)).strftime("%Y-%m-%d"),
                    end=(as_of + timedelta(days=1)).strftime("%Y-%m-%d"),
                )
            )
            levels[name] = float(hist["Close"].iloc[-1]) if hist is not None and not hist.empty else None

        hyg_lqd_spread_proxy = None
        if changes["HYG"] is not None and changes["LQD"] is not None:
            hyg_lqd_spread_proxy = changes["HYG"] - changes["LQD"]

        regime_tags = []
        if levels["VIX"] is not None:
            regime_tags.append("high_vol" if levels["VIX"] > 22 else "calm_vol")
        if changes["US10Y"] is not None:
            regime_tags.append("rates_up" if changes["US10Y"] > 0 else "rates_down")
        if hyg_lqd_spread_proxy is not None:
            regime_tags.append("credit_risk_on" if hyg_lqd_spread_proxy > 0 else "credit_defensive")
        regime_label = ", ".join(regime_tags) if regime_tags else "undetermined"

        lines = [
            f"# Macro Regime Snapshot as of {curr_date}",
            f"Regime label: {regime_label}",
            "",
            "## Proxy Levels and 1M Change",
        ]
        for name in ("VIX", "DXY", "US10Y", "WTI_OIL", "GOLD", "HYG", "LQD"):
            lines.append(f"- {name}: level={levels[name] if levels[name] is not None else 'N/A'}, 1M_change={_fmt_pct(changes[name])}")
        lines.append(
            f"- HYG-LQD 1M spread proxy: {_fmt_pct(hyg_lqd_spread_proxy)}"
        )
        return "\n".join(lines)
    except Exception as exc:
        return f"Error fetching macro regime data: {exc}"


def get_macro_regime_yfinance_complement(curr_date: str) -> str:
    """Oil, gold, credit ETFs, and ICE dollar index — complements FRED macro without duplicating VIX / Treasury."""
    try:
        as_of = _to_datetime(curr_date)
        proxies = {
            "WTI_OIL": "CL=F",
            "GOLD": "GC=F",
            "HYG": "HYG",
            "LQD": "LQD",
            "DXY_YF": "DX-Y.NYB",
        }
        lines = [
            f"# Complementary market proxies (yfinance) as of {curr_date}",
            "",
            "## Levels and ~1M change",
        ]
        hyg_ret: Optional[float] = None
        lqd_ret: Optional[float] = None
        for name, symbol in proxies.items():
            ret_1m = _history_return(symbol, as_of, 1)
            if symbol == "HYG":
                hyg_ret = ret_1m
            elif symbol == "LQD":
                lqd_ret = ret_1m
            hist = yf_retry(
                lambda s=symbol: yf.Ticker(s).history(
                    start=(as_of - timedelta(days=14)).strftime("%Y-%m-%d"),
                    end=(as_of + timedelta(days=1)).strftime("%Y-%m-%d"),
                )
            )
            level = float(hist["Close"].iloc[-1]) if hist is not None and not hist.empty else None
            lvl_s = f"{level:.4f}" if level is not None else "N/A"
            lines.append(f"- {name} ({symbol}): level={lvl_s}, 1M_change={_fmt_pct(ret_1m)}")
        spread = None if hyg_ret is None or lqd_ret is None else hyg_ret - lqd_ret
        lines.extend(["", f"- HYG minus LQD 1M spread proxy: {_fmt_pct(spread)}"])
        return "\n".join(lines)
    except Exception as exc:
        return f"Error fetching yfinance macro complement: {exc}"


def get_sector_etf_trends_yfinance(sector_or_etf: str, curr_date: str) -> str:
    """Return momentum and relative-strength summary for a sector ETF."""
    try:
        as_of = _to_datetime(curr_date)
        key = (sector_or_etf or "").strip()
        symbol = SECTOR_ETF_MAP.get(key.lower(), key.upper() if key else "SPY")

        r1m = _history_return(symbol, as_of, 1)
        r3m = _history_return(symbol, as_of, 3)
        r12m = _history_return(symbol, as_of, 12)
        spy12 = _history_return("SPY", as_of, 12)
        rs12 = None if r12m is None or spy12 is None else r12m - spy12

        momentum_class = "neutral"
        if r3m is not None and r12m is not None:
            if r3m > 0 and r12m > 0:
                momentum_class = "uptrend"
            elif r3m < 0 and r12m < 0:
                momentum_class = "downtrend"
            else:
                momentum_class = "mixed"

        lines = [
            f"# Sector ETF Trends for {sector_or_etf}",
            f"Resolved ETF symbol: {symbol}",
            f"As of trade date: {curr_date}",
            f"1M return: {_fmt_pct(r1m)}",
            f"3M return: {_fmt_pct(r3m)}",
            f"12M return: {_fmt_pct(r12m)}",
            f"12M relative strength vs SPY: {_fmt_pct(rs12)}",
            f"Momentum class: {momentum_class}",
        ]
        return "\n".join(lines)
    except Exception as exc:
        return f"Error fetching sector ETF trends for {sector_or_etf}: {exc}"


def get_options_implied_move_yfinance(ticker: str, curr_date: str) -> str:
    """Estimate implied move from nearest-expiry ATM straddle."""
    try:
        symbol = ticker.upper()
        as_of = _to_datetime(curr_date)
        tk = yf.Ticker(symbol)
        expiries = yf_retry(lambda: list(tk.options)) or []
        if not expiries:
            return f"No options expiries available for {symbol}"

        chosen_expiry = expiries[0]
        for expiry in expiries:
            expiry_dt = _to_datetime(expiry)
            if expiry_dt >= as_of:
                chosen_expiry = expiry
                break

        hist = yf_retry(
            lambda: tk.history(
                start=(as_of - timedelta(days=7)).strftime("%Y-%m-%d"),
                end=(as_of + timedelta(days=1)).strftime("%Y-%m-%d"),
            )
        )
        if hist is None or hist.empty:
            return f"No price history available for {symbol} around {curr_date}"
        spot = float(hist["Close"].iloc[-1])

        chain = yf_retry(lambda: tk.option_chain(chosen_expiry))
        calls = chain.calls
        puts = chain.puts
        if calls.empty or puts.empty:
            return f"No option chain data for {symbol} at expiry {chosen_expiry}"

        calls = calls.assign(dist=(calls["strike"] - spot).abs()).sort_values("dist")
        puts = puts.assign(dist=(puts["strike"] - spot).abs()).sort_values("dist")
        call_row = calls.iloc[0]
        put_row = puts.iloc[0]
        strike = float((call_row["strike"] + put_row["strike"]) / 2.0)
        straddle = float(call_row.get("lastPrice", 0.0) + put_row.get("lastPrice", 0.0))
        implied_move_pct = None if spot == 0 else (straddle / spot) * 100.0

        return "\n".join(
            [
                f"# Options Implied Move for {symbol}",
                f"Trade date: {curr_date}",
                f"Selected expiry: {chosen_expiry}",
                f"Reference spot: {spot:.4f}",
                f"Approx ATM strike: {strike:.4f}",
                f"ATM straddle price (call+put): {straddle:.4f}",
                f"Implied move to expiry: {implied_move_pct:.2f}%" if implied_move_pct is not None else "Implied move to expiry: N/A",
            ]
        )
    except Exception as exc:
        return f"Error fetching options implied move for {ticker}: {exc}"
