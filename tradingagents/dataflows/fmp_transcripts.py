"""Financial Modeling Prep earnings call transcript ingestion (optional API key)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from tradingagents.dataflows.api_file_cache import cache_get_json, cache_set_json
from tradingagents.dataflows.config import DataVendorSkipped

_BASE = "https://financialmodelingprep.com/stable"


def _api_key() -> Optional[str]:
    return (
        os.getenv("FMP_API_KEY", "").strip()
        or os.getenv("FINANCIAL_MODELING_PREP_API_KEY", "").strip()
        or None
    )


def _fmp_symbol(ticker: str) -> str:
    """FMP coverage is strongest for US symbols; strip common exchange suffixes."""
    base = (ticker or "").strip().upper()
    if "." in base:
        base = base.split(".", 1)[0]
    return base


def _get_json(url: str, params: Dict[str, Any]) -> Any:
    r = requests.get(url, params=params, timeout=45)
    r.raise_for_status()
    return r.json()


def _parse_anchor(curr_date: str) -> datetime:
    try:
        return datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError as exc:
        raise DataVendorSkipped(f"invalid curr_date for transcripts: {curr_date}") from exc


def get_earnings_transcript_highlights_fmp(ticker: str, curr_date: str) -> str:
    """Return the latest earnings call transcript available on or before trade_date."""
    key = _api_key()
    if not key:
        raise DataVendorSkipped("FMP_API_KEY (or FINANCIAL_MODELING_PREP_API_KEY) not set")

    sym = _fmp_symbol(ticker)
    if not sym:
        raise DataVendorSkipped("empty ticker for transcript lookup")

    anchor = _parse_anchor(curr_date)
    cache_key = f"fmp_tx_dates_{sym}_{curr_date}"
    cached = cache_get_json("fmp", cache_key, ttl_seconds=24 * 3600)

    if cached is None:
        try:
            dates_raw = _get_json(
                f"{_BASE}/earning-call-transcript-dates",
                {"symbol": sym, "apikey": key},
            )
        except requests.RequestException as exc:
            raise DataVendorSkipped(f"FMP transcript dates request failed: {exc}") from exc

        if isinstance(dates_raw, dict) and dates_raw.get("Error Message"):
            raise DataVendorSkipped(str(dates_raw.get("Error Message")))
        if not isinstance(dates_raw, list):
            raise DataVendorSkipped("unexpected FMP transcript dates payload")

        payload = {"fetched_at": datetime.now(timezone.utc).timestamp(), "dates": dates_raw}
        cache_set_json("fmp", cache_key, payload)
    else:
        dates_raw = cached.get("dates") or []

    picked = _pick_latest_quarter_before_anchor(dates_raw, anchor)
    if not picked:
        return (
            f"# Earnings Call Transcript ({sym})\n"
            f"As of trade date: {curr_date}\n"
            f"Source: Financial Modeling Prep (no transcript dated on/before trade date)\n\n"
            "Treat transcript-based claims as unavailable from tools."
        )

    year = int(picked["year"])
    quarter = int(picked["quarter"])
    tx_cache = f"fmp_tx_body_{sym}_{year}Q{quarter}"
    body_cached = cache_get_json("fmp", tx_cache, ttl_seconds=7 * 24 * 3600)
    if body_cached is None:
        try:
            tx_raw = _get_json(
                f"{_BASE}/earning-call-transcript",
                {"symbol": sym, "year": year, "quarter": quarter, "apikey": key},
            )
        except requests.RequestException as exc:
            raise DataVendorSkipped(f"FMP transcript fetch failed: {exc}") from exc

        if isinstance(tx_raw, dict) and tx_raw.get("Error Message"):
            raise DataVendorSkipped(str(tx_raw.get("Error Message")))

        cache_set_json(
            "fmp",
            tx_cache,
            {"fetched_at": datetime.now(timezone.utc).timestamp(), "transcript": tx_raw},
        )
    else:
        tx_raw = body_cached.get("transcript")

    content = _flatten_transcript_content(tx_raw)
    max_chars = 28000
    truncated_note = ""
    if len(content) > max_chars:
        content = content[:max_chars]
        truncated_note = f"\n\n_(Transcript truncated to {max_chars} characters for tool response.)_"

    call_date = picked.get("date") or ""
    lines = [
        f"# Earnings Call Transcript Highlights ({sym})",
        f"As of trade date: {curr_date}",
        f"Source: Financial Modeling Prep — fiscal year {year} Q{quarter}"
        + (f", call date {call_date}" if call_date else ""),
        "",
        "## Management discussion (excerpt)",
        content + truncated_note,
    ]
    return "\n".join(lines)


def _pick_latest_quarter_before_anchor(
    rows: List[Any],
    anchor: datetime,
) -> Optional[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            y = int(row.get("year") or row.get("fiscalYear") or row.get("fiscal_year"))
            q = int(row.get("quarter") or row.get("fiscalQuarter") or row.get("fiscal_quarter"))
        except (TypeError, ValueError):
            continue
        date_str = row.get("date") or row.get("transcriptDate") or row.get("earningDate") or ""
        dt: Optional[datetime] = None
        if date_str:
            try:
                dt = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
            except ValueError:
                dt = None
        if dt is not None and dt <= anchor:
            candidates.append({"year": y, "quarter": q, "date": date_str, "sort": dt})

    if not candidates:
        return None
    candidates.sort(key=lambda x: x["sort"], reverse=True)
    best = candidates[0]
    return {"year": best["year"], "quarter": best["quarter"], "date": best.get("date", "")}


def _flatten_transcript_content(tx_raw: Any) -> str:
    if tx_raw is None:
        return "(empty transcript payload)"
    if isinstance(tx_raw, str):
        return tx_raw.strip() or "(empty transcript)"
    if isinstance(tx_raw, list):
        parts: List[str] = []
        for block in tx_raw:
            if isinstance(block, dict):
                line = block.get("content") or block.get("text") or block.get("speech")
                speaker = block.get("speaker") or block.get("name")
                if line:
                    if speaker:
                        parts.append(f"**{speaker}**: {line}")
                    else:
                        parts.append(str(line))
            elif isinstance(block, str):
                parts.append(block)
        return "\n\n".join(parts).strip() or "(empty transcript)"
    if isinstance(tx_raw, dict):
        inner = tx_raw.get("content") or tx_raw.get("text") or tx_raw.get("transcript")
        if isinstance(inner, str):
            return inner.strip()
        if isinstance(inner, list):
            return _flatten_transcript_content(inner)
        # Single-object transcript (symbol/year/quarter + content fields)
        skip = {"symbol", "year", "quarter", "date", "cik"}
        text_bits = [str(v) for k, v in tx_raw.items() if k not in skip and isinstance(v, str)]
        if text_bits:
            return "\n\n".join(text_bits).strip()
    return str(tx_raw)
