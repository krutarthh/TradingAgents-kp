"""Dataset and scoring helpers for methodology eval loops (multi-horizon forward returns)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

import yfinance as yf


@dataclass(frozen=True)
class EvalCase:
    ticker: str
    trade_date: str
    sector: str = ""
    regime: str = ""
    volatility_bucket: str = ""
    earnings_window: bool = False


def _closest_prior_close(series, anchor: datetime):
    idx = series.index
    if getattr(idx, "tz", None) is not None and anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=idx.tz)
    elif getattr(idx, "tz", None) is None and anchor.tzinfo is not None:
        anchor = anchor.replace(tzinfo=None)
    valid = series.loc[idx <= anchor]
    if valid.empty:
        return None
    return float(valid["Close"].iloc[-1])


def compute_forward_return_label(
    ticker: str,
    trade_date: str,
    horizon_days: int,
    benchmark_ticker: str = "SPY",
    *,
    observable_through: Optional[date] = None,
) -> Optional[Dict[str, float]]:
    """Compute raw and benchmark-relative return over ``horizon_days`` calendar days.

    Uses prior closes on or before ``trade_date`` and on or before ``trade_date + horizon_days``.
    Returns None if the forward horizon extends beyond ``observable_through`` (default: today),
    or if Yahoo history is insufficient.

    Alpha vs benchmark: raw_stock - raw_benchmark over the same windows.
    """
    observable_through = observable_through or date.today()
    start_dt = datetime.strptime(trade_date, "%Y-%m-%d")
    end_dt = start_dt + timedelta(days=horizon_days)
    if end_dt.date() > observable_through:
        return None

    fetch_start = (start_dt - timedelta(days=7)).strftime("%Y-%m-%d")
    fetch_end = (end_dt + timedelta(days=7)).strftime("%Y-%m-%d")

    stock = yf.Ticker(ticker).history(start=fetch_start, end=fetch_end)
    bench = yf.Ticker(benchmark_ticker).history(start=fetch_start, end=fetch_end)
    if stock.empty or bench.empty:
        return None

    s0 = _closest_prior_close(stock, start_dt)
    s1 = _closest_prior_close(stock, end_dt)
    b0 = _closest_prior_close(bench, start_dt)
    b1 = _closest_prior_close(bench, end_dt)
    if any(v is None for v in (s0, s1, b0, b1)):
        return None
    if s0 == 0 or b0 == 0:
        return None

    raw = (s1 - s0) / s0
    alpha = raw - ((b1 - b0) / b0)
    return {
        "horizon_days": float(horizon_days),
        "raw_return": raw,
        "alpha_return": alpha,
    }


def compute_60d_label(
    ticker: str,
    trade_date: str,
    benchmark_ticker: str = "SPY",
) -> Optional[Dict[str, float]]:
    """Compute 60 calendar-day raw and alpha return labels (backward-compatible keys)."""
    out = compute_forward_return_label(ticker, trade_date, 60, benchmark_ticker)
    if not out:
        return None
    return {
        "raw_return_60d": out["raw_return"],
        "alpha_return_60d": out["alpha_return"],
    }


def build_eval_rows(
    cases: Iterable[EvalCase],
    benchmark_ticker: str = "SPY",
) -> List[Dict]:
    """Build frozen eval rows (60d only), skipping rows with unavailable labels."""
    rows: List[Dict] = []
    for case in cases:
        label = compute_60d_label(case.ticker, case.trade_date, benchmark_ticker)
        if not label:
            continue
        rows.append(
            {
                "ticker": case.ticker,
                "trade_date": case.trade_date,
                "sector": case.sector,
                "regime": case.regime,
                "volatility_bucket": case.volatility_bucket,
                "earnings_window": case.earnings_window,
                "benchmark_ticker": benchmark_ticker,
                **label,
            }
        )
    return rows


def validate_eval_rows(rows: List[Dict]) -> Tuple[bool, List[str]]:
    """Validate 60d eval rows for missing fields and duplicates."""
    errors: List[str] = []
    seen = set()
    required = ("ticker", "trade_date", "raw_return_60d", "alpha_return_60d", "benchmark_ticker")
    for idx, row in enumerate(rows):
        key = (row.get("ticker"), row.get("trade_date"))
        if key in seen:
            errors.append(f"duplicate row: {key}")
        seen.add(key)
        for k in required:
            if row.get(k) is None:
                errors.append(f"row {idx} missing required field: {k}")
    return (len(errors) == 0, errors)


def weighted_rubric_score(scores: Dict[str, float], weights: Optional[Dict[str, float]] = None) -> float:
    """Aggregate rubric scores with default weights (all equal)."""
    if not scores:
        return 0.0
    if weights is None:
        weights = {k: 1.0 for k in scores}
    denom = sum(max(0.0, float(weights.get(k, 0.0))) for k in scores)
    if denom <= 0:
        return 0.0
    num = sum(float(scores[k]) * max(0.0, float(weights.get(k, 0.0))) for k in scores)
    return num / denom


DEFAULT_REPLAY_EVAL_CASES: Tuple[EvalCase, ...] = (
    EvalCase(ticker="SPY", trade_date="2024-06-03"),
    EvalCase(ticker="AAPL", trade_date="2024-06-03"),
)


def enrich_eval_rows_with_rubric_metadata(rows: List[Dict]) -> List[Dict]:
    """Merge LangSmith-style dataset metadata into eval rows."""
    from tradingagents.evaluation.langsmith_rubric import suggested_langsmith_dataset_metadata

    out: List[Dict] = []
    for row in rows:
        ticker = row.get("ticker")
        td = row.get("trade_date")
        if ticker is None or td is None:
            raise ValueError("each row must include ticker and trade_date")
        meta = suggested_langsmith_dataset_metadata(str(ticker), str(td))
        merged = dict(row)
        merged.update(meta)
        out.append(merged)
    return out


def join_forward_labels_for_tickers(
    ticker: str,
    trade_date: str,
    horizons: Iterable[int],
    benchmark_ticker: str = "SPY",
    observable_through: Optional[date] = None,
) -> Dict[str, Optional[float]]:
    """Return flat dict keys raw_return_{h}d and alpha_return_{h}d for each horizon (or None)."""
    out: Dict[str, Optional[float]] = {}
    for h in horizons:
        label = compute_forward_return_label(
            ticker,
            trade_date,
            int(h),
            benchmark_ticker,
            observable_through=observable_through,
        )
        if label is None:
            out[f"raw_return_{h}d"] = None
            out[f"alpha_return_{h}d"] = None
        else:
            out[f"raw_return_{h}d"] = label["raw_return"]
            out[f"alpha_return_{h}d"] = label["alpha_return"]
    return out
