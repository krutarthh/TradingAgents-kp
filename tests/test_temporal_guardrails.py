"""Tests for point-in-time / temporal guardrails."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows import temporal
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.fred_macro import _latest_value, _render_fred_macro
from tradingagents.dataflows.api_ninjas_sec import get_sec_filing_highlights_ninjas
from tradingagents.dataflows.yfinance_forward import (
    get_analyst_estimates_yfinance,
    get_options_implied_move_yfinance,
)
from tradingagents.dataflows.cnn_sentiment import get_fear_greed_index_cnn
from tradingagents.dataflows.interface import route_to_vendor


@pytest.fixture(autouse=True)
def _reset_config():
    set_config({"eval_strict_temporal": False, "eval_cutoff_date": None})
    yield
    set_config({"eval_strict_temporal": False, "eval_cutoff_date": None})


def test_filter_observations_on_or_before():
    obs = [
        {"date": "2008-10-01", "value": "1"},
        {"date": "2008-08-01", "value": "2"},
        {"date": "2009-01-01", "value": "3"},
    ]
    out = temporal.filter_observations_on_or_before(obs, "2008-09-15")
    dates = {r["date"] for r in out}
    assert dates == {"2008-08-01"}
    assert "2009-01-01" not in dates
    assert "2008-10-01" not in dates


def test_latest_observation_on_or_before():
    obs = [
        {"date": "2009-01-01", "value": "99"},
        {"date": "2008-08-01", "value": "20"},
    ]
    val, d = temporal.latest_observation_on_or_before(obs, "2008-09-15")
    assert val == "20"
    assert d == "2008-08-01"


def test_fred_latest_value_respects_cutoff():
    obs = [
        {"date": "2025-01-01", "value": "99"},
        {"date": "2008-08-01", "value": "22"},
    ]
    val, d = _latest_value(obs, cutoff="2008-09-15")
    assert val == "22"
    assert d == "2008-08-01"


def test_filter_filings_on_or_before():
    rows = [
        {"filing_date": "2020-01-01"},
        {"filing_date": "2007-12-31"},
    ]
    out = temporal.filter_rows_on_or_before(rows, "2008-09-15")
    assert len(out) == 1
    assert out[0]["filing_date"] == "2007-12-31"


@patch("tradingagents.dataflows.api_ninjas_sec.cache_get_json", return_value=None)
@patch("tradingagents.dataflows.api_ninjas_sec.cache_set_json")
@patch("tradingagents.dataflows.api_ninjas_sec._fetch_sec_filings")
def test_sec_highlights_picks_pit_filing(mock_fetch, _set, _get):
    mock_fetch.return_value = [
        {"filing_date": "2024-01-01", "form_type": "10-K", "filing_url": "http://new"},
        {"filing_date": "2007-03-01", "form_type": "10-K", "filing_url": "http://old"},
    ]
    text = get_sec_filing_highlights_ninjas("AAPL", "2008-09-15")
    assert "2007-03-01" in text
    assert "2024-01-01" not in text


def test_analyst_estimates_strict_no_live_snapshot():
    set_config({"eval_strict_temporal": True})
    rec = pd.DataFrame({"grade": ["buy"]}, index=pd.to_datetime(["2008-01-01"]))
    mock_tk = MagicMock()
    mock_tk.recommendations = rec
    mock_tk.earnings_history = pd.DataFrame()
    with patch("tradingagents.dataflows.yfinance_forward.yf.Ticker", return_value=mock_tk):
        with patch("tradingagents.dataflows.yfinance_forward.yf_retry", side_effect=lambda f: f()):
            out = get_analyst_estimates_yfinance("AAPL", "2008-09-15")
    assert "Data as-of: 2008-09-15" in out
    assert "targetMeanPrice" not in out.lower()
    assert "Data retrieved on" not in out


def test_options_skip_in_strict_mode():
    set_config({"eval_strict_temporal": True})
    out = get_options_implied_move_yfinance("AAPL", "2008-09-15")
    assert "strict historical mode" in out.lower()


def test_fear_greed_skips_in_strict_mode():
    set_config({"eval_strict_temporal": True})
    out = get_fear_greed_index_cnn("2008-09-15")
    assert "strict historical mode" in out.lower()
    routed = route_to_vendor("get_fear_greed_index", "2008-09-15")
    assert "strict historical mode" in routed.lower()
    assert "[tool=get_fear_greed_index]" in routed
