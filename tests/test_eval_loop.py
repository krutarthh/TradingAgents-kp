"""Tests for 60d evaluation loop utilities."""

from unittest.mock import patch

import pandas as pd
import pytest

from tradingagents.evaluation.eval_loop import (
    EvalCase,
    build_eval_rows,
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
