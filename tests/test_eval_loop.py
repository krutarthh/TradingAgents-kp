"""Tests for 60d evaluation loop utilities."""

from unittest.mock import patch

import pandas as pd
import pytest

from tradingagents.evaluation.eval_loop import (
    DEFAULT_REPLAY_EVAL_CASES,
    EvalCase,
    build_eval_rows,
    enrich_eval_rows_with_rubric_metadata,
    validate_eval_rows,
    weighted_rubric_score,
)


@pytest.mark.unit
def test_build_eval_rows_and_validate():
    idx = pd.to_datetime(["2026-01-02", "2026-03-03"])
    df = pd.DataFrame({"Close": [100.0, 110.0]}, index=idx)
    with patch("yfinance.Ticker") as tkr:
        tkr.return_value.history.return_value = df
        rows = build_eval_rows([EvalCase(ticker="NVDA", trade_date="2026-01-02")], "SPY")
    assert len(rows) == 1
    ok, errors = validate_eval_rows(rows)
    assert ok
    assert not errors


@pytest.mark.unit
def test_weighted_rubric_score():
    scores = {"a": 2.0, "b": 1.0}
    weights = {"a": 2.0, "b": 1.0}
    out = weighted_rubric_score(scores, weights)
    assert out == pytest.approx((2.0 * 2.0 + 1.0 * 1.0) / 3.0)


@pytest.mark.unit
def test_enrich_eval_rows_with_rubric_metadata():
    rows = [
        {
            "ticker": "AAPL",
            "trade_date": "2024-01-02",
            "raw_return_60d": 0.01,
            "alpha_return_60d": 0.0,
        }
    ]
    out = enrich_eval_rows_with_rubric_metadata(rows)
    assert out[0]["rubric_version"] == "methodology_first_v1"
    assert out[0]["benchmark_ticker"] == "SPY"
    assert out[0]["horizon_days"] == 60


@pytest.mark.unit
def test_default_replay_eval_cases_well_formed():
    assert len(DEFAULT_REPLAY_EVAL_CASES) >= 1
    assert all(c.ticker and c.trade_date for c in DEFAULT_REPLAY_EVAL_CASES)
