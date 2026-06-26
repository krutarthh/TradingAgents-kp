"""Process-pool worker for pipeline eval (importable module for multiprocessing spawn)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

# Rich-signal columns lifted from the structured PM decision (final_decision_signal).
_SIGNAL_COLUMNS = (
    "rating_score",
    "directional_score",
    "confidence",
    "price_target",
    "time_horizon",
    "bull_case_target",
    "base_case_target",
    "bear_case_target",
    "bull_probability",
    "base_probability",
    "bear_probability",
    "trader_action",
    "decision_consistency",
    "rating_parse_failed",
    "structured_fallback_used",
)


def _rating_bucket(rating: str) -> str:
    from tradingagents.agents.utils.rating import rating_bucket

    return rating_bucket(rating)


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

    from tradingagents.evaluation.eval_loop import (
        compute_trailing_return,
        join_forward_labels_for_tickers,
    )
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    ticker = str(job["ticker"]).strip().upper()
    anchor = str(job["anchor"])
    horizons: List[int] = list(job["horizons"])
    benchmark = str(job["benchmark"])
    run_date = date.fromisoformat(str(job["run_date_iso"]))
    cfg: Dict[str, Any] = dict(job["config"])
    cfg["eval_cutoff_date"] = anchor
    cfg["eval_strict_temporal"] = cfg.get("eval_strict_temporal", True)

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
    for col in _SIGNAL_COLUMNS:
        row[col] = ""

    labels = join_forward_labels_for_tickers(
        ticker,
        anchor,
        horizons,
        benchmark,
        observable_through=run_date,
    )
    row.update(labels)

    # Point-in-time trailing return -> momentum baseline input (no look-ahead).
    trailing = compute_trailing_return(ticker, anchor, lookback_days=90)
    row["prior_return_trailing"] = trailing if trailing is not None else ""

    try:
        graph = TradingAgentsGraph(config=cfg, debug=False)
        final_state, rating_signal = graph.propagate(ticker, anchor)
        rating = rating_signal if isinstance(rating_signal, str) else str(rating_signal)
        row["rating"] = rating
        row["rating_bucket"] = _rating_bucket(rating)

        signal = (final_state or {}).get("final_decision_signal") or {}
        if signal.get("rating_bucket") and signal["rating_bucket"] != "unparsed":
            # Authoritative bucket from the structured decision (avoids a false
            # neutral when prose mentions a rating word before the label line).
            row["rating_bucket"] = signal["rating_bucket"]
        for col in _SIGNAL_COLUMNS:
            val = signal.get(col)
            if val is not None:
                row[col] = val
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["rating"] = ""
        row["rating_bucket"] = ""

    return row
