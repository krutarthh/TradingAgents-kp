"""Tests for pipeline eval parallel worker."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.evaluation.parallel_worker import run_single_pipeline_eval


@pytest.mark.unit
def test_run_single_pipeline_eval_returns_row_with_labels(monkeypatch):
    job = {
        "root": "/tmp",
        "config": {
            "llm_provider": "ollama",
            "quick_think_llm": "gemma4:31b-cloud",
            "deep_think_llm": "gemma4:31b-cloud",
            "results_dir": "/tmp/ta_eval",
            "data_cache_dir": "/tmp/cache",
            "memory_log_path": "/tmp/mem.md",
            "checkpoint_enabled": False,
            "max_recur_limit": 50,
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
        },
        "ticker": "AAPL",
        "anchor": "2020-05-12",
        "horizons": [60],
        "benchmark": "SPY",
        "run_date_iso": date(2026, 1, 1).isoformat(),
        "llm_provider": "ollama",
        "quick_think_llm": "gemma4:31b-cloud",
        "deep_think_llm": "gemma4:31b-cloud",
    }

    with patch("tradingagents.evaluation.eval_loop.join_forward_labels_for_tickers") as jf:
        jf.return_value = {"raw_return_60d": 0.01, "alpha_return_60d": 0.0}
        with patch("tradingagents.graph.trading_graph.TradingAgentsGraph") as TG:
            inst = MagicMock()
            inst.propagate.return_value = ({}, "Buy")
            TG.return_value = inst
            row = run_single_pipeline_eval(job)

    assert row["ticker"] == "AAPL"
    assert row["trade_date"] == "2020-05-12"
    assert row["rating"] == "Buy"
    assert row["rating_bucket"] == "bullish"
    assert row["alpha_return_60d"] == 0.0
    assert not row["error"]
