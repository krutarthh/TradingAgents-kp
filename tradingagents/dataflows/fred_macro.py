"""FRED macro series — batched per calendar day with disk cache (minimal API calls)."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from tradingagents.dataflows.api_file_cache import cache_get_json, cache_set_json
from .config import DataVendorSkipped


FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"

# Core series for agent macro / news context (expand as needed)
MACRO_SERIES: Dict[str, str] = {
    "VIXCLS": "CBOE Volatility Index (VIX)",
    "DGS10": "10-Year Treasury Constant Maturity Rate (%)",
    "T10Y2Y": "10-Year minus 2-Year Treasury spread",
    "DTWEXBGS": "Trade Weighted U.S. Dollar Index, Broad",
    "UNRATE": "Unemployment rate (%, SA)",
    "CPIAUCSL": "CPI All Urban Consumers (index, SA)",
    "NFCI": "National Financial Conditions Index (Chicago Fed)",
}


def _fred_api_key() -> Optional[str]:
    return os.getenv("FRED_API_KEY", "").strip() or None


def _observations_for_series(
    series_id: str,
    api_key: str,
    observation_start: str,
    limit: int = 24,
) -> List[Dict[str, Any]]:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": observation_start,
        "sort_order": "desc",
        "limit": limit,
    }
    r = requests.get(FRED_OBS_URL, params=params, timeout=45)
    r.raise_for_status()
    data = r.json()
    obs = data.get("observations") or []
    return obs


def get_macro_regime_fred(curr_date: str) -> str:
    """Build macro regime text from official FRED series.

    Uses one cache file per (curr_date) containing all series — at most one HTTP
    round per cold start per day for personal / free-tier efficiency.
    """
    key = _fred_api_key()
    if not key:
        raise DataVendorSkipped("FRED_API_KEY not set")

    try:
        datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError as e:
        return f"Invalid curr_date for FRED macro: {curr_date} ({e})"

    # Refresh intraday at most every 6 hours (FRED dailies update slowly)
    ttl = 6 * 3600
    cache_key = f"fred_macro_bundle_{curr_date}"
    cached = cache_get_json("fred", cache_key, ttl)
    if cached is not None:
        return _render_fred_macro(curr_date, cached, source_note="(cached bundle)")

    start = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=400)).strftime("%Y-%m-%d")
    bundle: Dict[str, Any] = {"fetched_at": time.time(), "series": {}}
    # Sequential requests; FRED free tier is generous. Small pause avoids burst throttling.
    for sid in MACRO_SERIES:
        try:
            bundle["series"][sid] = _observations_for_series(sid, key, start, limit=30)
            time.sleep(0.15)
        except requests.RequestException as exc:
            bundle["series"][sid] = {"error": str(exc)}

    cache_set_json("fred", cache_key, bundle)
    return _render_fred_macro(curr_date, bundle, source_note="(live FRED API)")


def _latest_value(obs: Any) -> tuple[str, str]:
    if isinstance(obs, dict) and "error" in obs:
        return "N/A", str(obs["error"])
    if not isinstance(obs, list) or not obs:
        return "N/A", "no observations"
    for row in obs:
        val = row.get("value", ".")
        if val in (".", ""):
            continue
        return str(val), str(row.get("date", ""))
    return "N/A", "no numeric observations"


def _pct_change_from_obs(obs: Any, months_back: int = 1) -> Optional[float]:
    """Approximate change using observation roughly `months_back` months earlier."""
    if not isinstance(obs, list) or len(obs) < 2:
        return None
    try:
        latest = None
        for row in obs:
            v = row.get("value", ".")
            if v not in (".", ""):
                latest = float(v)
                latest_date = row.get("date")
                break
        if latest is None:
            return None
        # Walk observations to find one at least ~20 business days older
        anchor_idx = min(len(obs) - 1, max(20, months_back * 21))
        past = None
        for row in obs[anchor_idx:]:
            v = row.get("value", ".")
            if v not in (".", ""):
                past = float(v)
                break
        if past is None or past == 0:
            return None
        return (latest - past) / abs(past)
    except (ValueError, TypeError, IndexError):
        return None


def _render_fred_macro(curr_date: str, bundle: Dict[str, Any], source_note: str) -> str:
    series_block = bundle.get("series") or {}
    lines = [
        f"# Macro Regime Snapshot (FRED) as of {curr_date} {source_note}",
        "",
        "## Latest levels (official series)",
    ]
    for sid, title in MACRO_SERIES.items():
        obs = series_block.get(sid)
        val, d = _latest_value(obs)
        lines.append(f"- **{sid}** ({title}): {val} (obs date: {d})")

    lines.extend(["", "## Approximate recent change (vs ~1 month earlier in series)"])
    for sid in ("VIXCLS", "DGS10", "DTWEXBGS", "UNRATE", "NFCI"):
        obs = series_block.get(sid)
        ch = _pct_change_from_obs(obs, months_back=1)
        if ch is None:
            lines.append(f"- {sid}: N/A")
        else:
            lines.append(f"- {sid}: {ch * 100:+.2f}% (approx)")

    vix_obs = series_block.get("VIXCLS")
    vix_val, _ = _latest_value(vix_obs)
    tags = []
    try:
        vix_f = float(vix_val) if vix_val not in ("N/A", "") else None
        if vix_f is not None:
            tags.append("high_vol" if vix_f > 22 else "calm_vol")
    except ValueError:
        pass
    t10y2y_obs = series_block.get("T10Y2Y")
    ty_val, _ = _latest_value(t10y2y_obs)
    try:
        ty_f = float(ty_val) if ty_val not in ("N/A", "") else None
        if ty_f is not None:
            tags.append("curve_inverted" if ty_f < 0 else "curve_positive")
    except ValueError:
        pass

    lines.extend(["", f"## Regime tags: {', '.join(tags) if tags else 'undetermined'}"])
    return "\n".join(lines)
