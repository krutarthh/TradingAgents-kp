"""Preflight checks for pipeline eval: Yahoo price availability per horizon."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from tradingagents.evaluation.eval_loop import compute_forward_return_label


@dataclass
class PreflightRow:
    ticker: str
    anchor: str
    horizon_days: int
    ok: bool
    detail: str


def load_universe_json(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def horizon_observable(anchor: str, horizon_days: int, run_date: Optional[date] = None) -> bool:
    """True if anchor + horizon is not after wall-clock today (labels exist)."""
    run_date = run_date or date.today()
    end = datetime.strptime(anchor, "%Y-%m-%d").date() + timedelta(days=horizon_days)
    return end <= run_date


def preflight_pairs(
    tickers: Sequence[str],
    anchors: Sequence[str],
    horizons: Sequence[int],
    benchmark_ticker: str = "SPY",
    run_date: Optional[date] = None,
) -> List[PreflightRow]:
    """Return one PreflightRow per (ticker, anchor, horizon)."""
    rows: List[PreflightRow] = []
    run_date = run_date or date.today()

    for ticker in tickers:
        t = ticker.strip().upper()
        for anchor in anchors:
            for h in horizons:
                if not horizon_observable(anchor, h, run_date):
                    rows.append(
                        PreflightRow(
                            ticker=t,
                            anchor=anchor,
                            horizon_days=h,
                            ok=False,
                            detail=f"forward end date after run_date ({run_date}); label not yet observable",
                        )
                    )
                    continue
                label = compute_forward_return_label(t, anchor, h, benchmark_ticker)
                if label is None:
                    rows.append(
                        PreflightRow(
                            ticker=t,
                            anchor=anchor,
                            horizon_days=h,
                            ok=False,
                            detail="missing Yahoo bars or invalid prices at anchor/horizon",
                        )
                    )
                else:
                    rows.append(
                        PreflightRow(
                            ticker=t,
                            anchor=anchor,
                            horizon_days=h,
                            ok=True,
                            detail="ok",
                        )
                    )
    return rows


def preflight_report(rows: Sequence[PreflightRow]) -> Dict[str, Any]:
    """Aggregate counts for CLI / JSON export."""
    total = len(rows)
    ok_n = sum(1 for r in rows if r.ok)
    return {
        "total_checks": total,
        "ok": ok_n,
        "fail": total - ok_n,
        "rows": [
            {
                "ticker": r.ticker,
                "anchor": r.anchor,
                "horizon_days": r.horizon_days,
                "ok": r.ok,
                "detail": r.detail,
            }
            for r in rows
        ],
    }
