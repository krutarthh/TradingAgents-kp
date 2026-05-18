"""Point-in-time / cutoff helpers for historical eval and strict temporal mode."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from tradingagents.dataflows.config import get_config


def is_strict_temporal() -> bool:
    return bool(get_config().get("eval_strict_temporal"))


def eval_cutoff_date() -> Optional[str]:
    """Default as-of date from eval harness config (YYYY-MM-DD)."""
    raw = get_config().get("eval_cutoff_date")
    if raw is None or raw == "":
        return None
    return str(raw).strip()


def parse_cutoff(date_str: str) -> date:
    return datetime.strptime(date_str.strip()[:10], "%Y-%m-%d").date()


def data_as_of_header(cutoff: Optional[str]) -> str:
    if cutoff:
        return f"# Data as-of: {cutoff}\n"
    return ""


def pit_cache_key(*parts: str) -> str:
    return "_".join(p.strip() for p in parts if p and str(p).strip())


def assert_range_end_on_or_before(end_date: str, cutoff: str) -> None:
    """Raise ValueError if end_date is after cutoff (strict checks)."""
    if not is_strict_temporal():
        return
    if parse_cutoff(end_date) > parse_cutoff(cutoff):
        raise ValueError(f"end_date {end_date} is after cutoff {cutoff}")


def filter_rows_on_or_before(
    rows: Sequence[Mapping[str, Any]],
    cutoff: str,
    date_field: str = "filing_date",
) -> List[Dict[str, Any]]:
    cut = parse_cutoff(cutoff)
    out: List[Dict[str, Any]] = []
    for row in rows:
        raw = row.get(date_field) or row.get("date") or ""
        if not raw:
            continue
        try:
            d = parse_cutoff(str(raw)[:10])
        except ValueError:
            continue
        if d <= cut:
            out.append(dict(row))
    return out


def filter_observations_on_or_before(
    observations: Sequence[Mapping[str, Any]],
    cutoff: str,
) -> List[Dict[str, Any]]:
    cut = parse_cutoff(cutoff)
    out: List[Dict[str, Any]] = []
    for row in observations:
        raw = row.get("date", "")
        if not raw:
            continue
        try:
            d = parse_cutoff(str(raw)[:10])
        except ValueError:
            continue
        if d <= cut:
            out.append(dict(row))
    return out


def latest_observation_on_or_before(
    observations: Sequence[Mapping[str, Any]],
    cutoff: str,
) -> tuple[str, str]:
    """Return (value, obs_date) for newest observation with date <= cutoff."""
    eligible = filter_observations_on_or_before(observations, cutoff)
    if not eligible:
        return "N/A", "no observations on or before cutoff"
    # Observations often sorted desc from API
    for row in eligible:
        val = row.get("value", ".")
        if val not in (".", "", None):
            return str(val), str(row.get("date", ""))
    return "N/A", "no numeric observations on or before cutoff"


def filter_dataframe_index_on_or_before(df, cutoff: str):
    """Filter a DataFrame with DatetimeIndex or date column <= cutoff."""
    import pandas as pd

    if df is None or getattr(df, "empty", True):
        return df
    cut_ts = pd.Timestamp(cutoff)
    if isinstance(df.index, pd.DatetimeIndex):
        return df.loc[df.index <= cut_ts]
    if "Date" in df.columns:
        return df[pd.to_datetime(df["Date"]) <= cut_ts]
    return df


def skip_live_only_message(tool_name: str, cutoff: str, reason: str) -> str:
    return (
        f"# {tool_name} unavailable in strict historical mode\n"
        f"As-of trade date: {cutoff}\n"
        f"Reason: {reason}\n"
    )


# Static sector + peers for strict mode (avoid live yfinance .info and modern mega-cap lists).
TICKER_SECTOR_STRICT: Dict[str, str] = {
    "AAPL": "technology",
    "MSFT": "technology",
    "NVDA": "technology",
    "TSM": "technology",
    "CSCO": "technology",
    "INTC": "technology",
    "GOOGL": "technology",
    "META": "technology",
    "JPM": "financial services",
    "BAC": "financial services",
    "GS": "financial services",
    "MS": "financial services",
    "WFC": "financial services",
    "XOM": "energy",
    "CVX": "energy",
    "UNH": "healthcare",
    "JNJ": "healthcare",
    "PFE": "healthcare",
    "WMT": "consumer defensive",
    "COST": "consumer defensive",
    "CAT": "industrials",
    "BA": "industrials",
    "LEN": "consumer cyclical",
    "DHI": "consumer cyclical",
}

# Peers appropriate for dot-com / pre-GFC era (no META, limited GOOGL).
SECTOR_PEERS_STRICT: Dict[str, List[str]] = {
    "technology": ["MSFT", "CSCO", "INTC", "ORCL", "IBM", "AAPL"],
    "healthcare": ["JNJ", "PFE", "MRK", "ABT", "BMY", "UNH"],
    "financial services": ["JPM", "BAC", "C", "WFC", "GS", "MS"],
    "financial": ["JPM", "BAC", "C", "WFC", "GS", "MS"],
    "consumer cyclical": ["HD", "LOW", "TGT", "LEN", "DHI", "F"],
    "consumer defensive": ["WMT", "PG", "KO", "PEP", "COST", "CL"],
    "industrials": ["CAT", "DE", "BA", "GE", "UNP", "HON"],
    "energy": ["XOM", "CVX", "COP", "SLB", "BP", "RDS-A"],
    "utilities": ["DUK", "SO", "EXC", "AEP", "NEE", "XEL"],
    "real estate": ["SPG", "PLD", "AMT", "EQR", "VTR", "O"],
    "communication services": ["T", "VZ", "DIS", "CMCSA", "TWX", "VIA"],
    "materials": ["DD", "DOW", "APD", "ECL", "NEM", "FCX"],
}


def strict_sector_for_ticker(ticker: str) -> str:
    return TICKER_SECTOR_STRICT.get(ticker.upper().strip(), "technology")


def strict_peers_for_sector(sector_key: str, symbol: str, max_peers: int = 5) -> List[str]:
    peers = SECTOR_PEERS_STRICT.get(sector_key.lower(), SECTOR_PEERS_STRICT["technology"])
    sym = symbol.upper()
    return [p for p in peers if p != sym][:max_peers]
