"""Process-pool worker for pipeline eval (importable module for multiprocessing spawn)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List


def _rating_bucket(rating: str) -> str:
    r = (rating or "").strip().lower()
    if r in ("buy", "overweight"):
        return "bullish"
    if r in ("sell", "underweight"):
        return "bearish"
    return "neutral"


def run_single_pipeline_eval(job: Dict[str, Any]) -> Dict[str, Any]:
    """Execute one (ticker, anchor) graph run in an isolated process.

    ``job`` must include: root (str), config (dict), ticker, anchor, horizons,
    benchmark, run_date_iso, llm_provider, quick_think_llm, deep_think_llm.
    """
    root = Path(job["root"])
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")
    except ImportError:
        pass

    from tradingagents.evaluation.eval_loop import join_forward_labels_for_tickers
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    ticker = str(job["ticker"]).strip().upper()
    anchor = str(job["anchor"])
    horizons: List[int] = list(job["horizons"])
    benchmark = str(job["benchmark"])
    run_date = date.fromisoformat(str(job["run_date_iso"]))
    cfg: Dict[str, Any] = dict(job["config"])

    row: Dict[str, Any] = {
        "ticker": ticker,
        "trade_date": anchor,
        "rating": "",
        "rating_bucket": "",
        "error": "",
        "llm_provider": job.get("llm_provider", ""),
        "quick_think_llm": job.get("quick_think_llm", ""),
        "deep_think_llm": job.get("deep_think_llm", ""),
    }
    labels = join_forward_labels_for_tickers(
        ticker,
        anchor,
        horizons,
        benchmark,
        observable_through=run_date,
    )
    row.update(labels)

    try:
        graph = TradingAgentsGraph(config=cfg, debug=False)
        _final_state, rating_signal = graph.propagate(ticker, anchor)
        rating = rating_signal if isinstance(rating_signal, str) else str(rating_signal)
        row["rating"] = rating
        row["rating_bucket"] = _rating_bucket(rating)
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["rating"] = ""
        row["rating_bucket"] = ""

    return row
