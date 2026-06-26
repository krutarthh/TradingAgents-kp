"""Append-only CSV log for live trading decisions (shadow book).

Each pipeline run with ``live_shadow_book_path`` set in config appends one row
with the PM ``final_decision_signal`` and metadata. After the holding period,
``review_shadow_book`` joins forward returns and runs ``metrics.summarize_rows``.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yfinance as yf

from tradingagents.evaluation.metrics import DEFAULT_HOLD_BAND, summarize_predictions

SHADOW_BOOK_COLUMNS = [
    "logged_at",
    "ticker",
    "trade_date",
    "rating",
    "rating_bucket",
    "directional_score",
    "confidence",
    "bull_probability",
    "base_probability",
    "bear_probability",
    "price_target",
    "trader_reconciled",
    "rating_parse_failed",
    "signal_json",
]


def append_shadow_book_row(
    path: str | Path,
    ticker: str,
    trade_date: str,
    signal: Dict[str, Any],
) -> None:
    """Append one live decision row to the shadow book CSV."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    write_header = not p.exists() or p.stat().st_size == 0
    row = {
        "logged_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ticker": ticker.upper(),
        "trade_date": trade_date,
        "rating": signal.get("rating", ""),
        "rating_bucket": signal.get("rating_bucket", ""),
        "directional_score": signal.get("directional_score", ""),
        "confidence": signal.get("confidence", ""),
        "bull_probability": signal.get("bull_probability", ""),
        "base_probability": signal.get("base_probability", ""),
        "bear_probability": signal.get("bear_probability", ""),
        "price_target": signal.get("price_target", ""),
        "trader_reconciled": signal.get("trader_reconciled", ""),
        "rating_parse_failed": signal.get("rating_parse_failed", ""),
        "signal_json": json.dumps(signal, default=str),
    }
    with open(p, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SHADOW_BOOK_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _forward_return(ticker: str, trade_date: str, holding_days: int) -> Optional[float]:
    start = datetime.strptime(trade_date, "%Y-%m-%d")
    end = start + timedelta(days=holding_days + 10)
    try:
        data = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if data is None or data.empty:
            return None
        close = data["Close"]
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        start_px = float(close.iloc[0])
        target_idx = min(holding_days, len(close) - 1)
        end_px = float(close.iloc[target_idx])
        if start_px == 0:
            return None
        return (end_px - start_px) / start_px
    except Exception:
        return None


def review_shadow_book(
    path: str | Path,
    holding_days: int = 60,
    benchmark: str = "SPY",
    hold_band: float = DEFAULT_HOLD_BAND,
) -> Dict[str, Any]:
    """Load shadow book rows, join forward returns where mature, return metrics summary."""
    p = Path(path)
    if not p.exists():
        return {"error": f"shadow book not found: {p}"}

    with open(p, newline="", encoding="utf-8") as f:
        rows: List[Dict[str, Any]] = list(csv.DictReader(f))

    today = datetime.utcnow().date()
    enriched: List[Dict[str, Any]] = []
    for row in rows:
        trade_date = row.get("trade_date") or ""
        ticker = row.get("ticker") or ""
        try:
            anchor = datetime.strptime(trade_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if (today - anchor).days < holding_days:
            continue
        raw = _forward_return(ticker, trade_date, holding_days)
        bench = _forward_return(benchmark, trade_date, holding_days)
        out = dict(row)
        out[f"raw_return_{holding_days}d"] = raw
        out[f"alpha_return_{holding_days}d"] = (
            None if raw is None or bench is None else raw - bench
        )
        enriched.append(out)

    summary = summarize_predictions(enriched, horizons=[holding_days], hold_band=hold_band)
    return {
        "path": str(p),
        "total_rows": len(rows),
        "mature_rows": len(enriched),
        "holding_days": holding_days,
        "metrics": summary,
    }
