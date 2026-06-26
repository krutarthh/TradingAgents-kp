"""Alpha Vantage earnings-call transcript connector (second transcript vendor).

Provides a failover for earnings transcripts so the pipeline no longer depends
on a single optional FMP key (otherwise it silently falls back to a stub). Uses
Alpha Vantage's ``EARNINGS_CALL_TRANSCRIPT`` function, walking back up to four
quarters from the trade date to find the latest available transcript.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional, Tuple

from tradingagents.dataflows.alpha_vantage_common import _make_api_request
from tradingagents.dataflows.config import DataVendorSkipped


def _recent_quarters(curr_date: str, n: int = 4) -> List[str]:
    """Return up to ``n`` fiscal-quarter labels (YYYYQX) ending on/before curr_date."""
    dt = datetime.strptime(curr_date, "%Y-%m-%d")
    year = dt.year
    q = (dt.month - 1) // 3 + 1
    # Step back one quarter so we reference a completed/reported quarter.
    out: List[str] = []
    for _ in range(n):
        q -= 1
        if q == 0:
            q = 4
            year -= 1
        out.append(f"{year}Q{q}")
    return out


def _flatten(payload) -> str:
    if isinstance(payload, dict):
        transcript = payload.get("transcript")
        if isinstance(transcript, list):
            parts = []
            for blk in transcript:
                if isinstance(blk, dict):
                    speaker = blk.get("speaker") or ""
                    content = blk.get("content") or ""
                    if content:
                        parts.append(f"**{speaker}**: {content}" if speaker else content)
            return "\n\n".join(parts)
    return ""


def get_earnings_transcript_alpha_vantage(ticker: str, curr_date: str) -> str:
    """Latest Alpha Vantage earnings transcript on/before trade date."""
    try:
        datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError as exc:
        raise DataVendorSkipped(f"invalid curr_date for AV transcript: {curr_date}") from exc

    sym = (ticker or "").strip().upper().split(".")[0]
    if not sym:
        raise DataVendorSkipped("empty ticker for AV transcript lookup")

    picked: Optional[Tuple[str, str]] = None
    try:
        for quarter in _recent_quarters(curr_date):
            raw = _make_api_request("EARNINGS_CALL_TRANSCRIPT", {"symbol": sym, "quarter": quarter})
            try:
                payload = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                continue
            content = _flatten(payload)
            if content.strip():
                picked = (quarter, content)
                break
    except ValueError as exc:
        # get_api_key raises ValueError when ALPHA_VANTAGE_API_KEY is missing.
        raise DataVendorSkipped(str(exc)) from exc

    if picked is None:
        return (
            f"# Earnings Call Transcript ({sym})\n"
            f"As of trade date: {curr_date}\n"
            "Source: Alpha Vantage (no transcript found in the last four quarters)\n\n"
            "Treat transcript-based claims as unavailable from tools."
        )

    quarter, content = picked
    max_chars = 28000
    note = ""
    if len(content) > max_chars:
        content = content[:max_chars]
        note = f"\n\n_(Transcript truncated to {max_chars} characters for tool response.)_"
    return "\n".join(
        [
            f"# Earnings Call Transcript Highlights ({sym})",
            f"As of trade date: {curr_date}",
            f"Source: Alpha Vantage — {quarter}",
            "",
            "## Management discussion (excerpt)",
            content + note,
        ]
    )
