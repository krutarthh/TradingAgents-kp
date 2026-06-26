"""Tests for live analysis quality improvements."""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import patch

import pytest

from tradingagents.dataflows.config import DataVendorSkipped


def test_sec_ticker_candidates_goog_prefers_googl():
    from tradingagents.dataflows.api_ninjas_sec import _sec_ticker_candidates

    assert _sec_ticker_candidates("GOOG") == ["GOOGL", "GOOG"]


def test_yfinance_indicators_include_new_keys():
    from tradingagents.dataflows import y_finance as yf_mod
    import inspect

    src = inspect.getsource(yf_mod.get_stock_stats_indicators_window)
    assert "close_20_sma" in src
    assert "volume_20_sma" in src


def test_finnhub_news_skips_without_key(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("FINNHUB_TOKEN", raising=False)
    from tradingagents.dataflows.finnhub_news import get_news_finnhub

    with pytest.raises(DataVendorSkipped):
        get_news_finnhub("AAPL", "2026-01-01", "2026-01-15")


def test_finnhub_news_routed_in_interface():
    from tradingagents.dataflows import interface

    assert "finnhub" in interface.VENDOR_METHODS["get_news"]
    assert "finnhub" in interface.VENDOR_METHODS["get_earnings_calendar"]


def test_live_shadow_book_append_and_review(tmp_path: Path):
    from tradingagents.evaluation.live_shadow_book import (
        append_shadow_book_row,
        review_shadow_book,
    )

    book = tmp_path / "shadow.csv"
    signal = {
        "rating": "buy",
        "rating_bucket": "bullish",
        "directional_score": 0.4,
        "confidence": 0.55,
        "bull_probability": 0.55,
        "base_probability": 0.3,
        "bear_probability": 0.15,
        "price_target": 200.0,
    }
    append_shadow_book_row(book, "AAPL", "2020-01-02", signal)
    assert book.exists()
    with open(book, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAPL"

    with patch(
        "tradingagents.evaluation.live_shadow_book._forward_return",
        side_effect=[0.05, 0.02],
    ):
        report = review_shadow_book(book, holding_days=60)
    assert report["mature_rows"] == 1
    assert "metrics" in report


def test_peer_comparables_includes_valuation_table(monkeypatch):
    from tradingagents.dataflows.yfinance_forward import get_peer_comparables_yfinance

    monkeypatch.setattr(
        "tradingagents.dataflows.yfinance_forward.is_strict_temporal",
        lambda: False,
    )
    monkeypatch.setattr(
        "tradingagents.dataflows.yfinance_forward._history_return",
        lambda sym, as_of, months: 0.1,
    )
    monkeypatch.setattr(
        "tradingagents.dataflows.yfinance_forward._valuation_multiples",
        lambda sym: {
            "trailingPE": 20.0,
            "forwardPE": 18.0,
            "enterpriseToEbitda": 12.0,
            "priceToSalesTrailing12Months": 5.0,
            "revenueGrowth": 0.08,
            "earningsGrowth": 0.1,
        },
    )
    monkeypatch.setattr(
        "tradingagents.dataflows.yfinance_forward.yf_retry",
        lambda fn: {"sector": "Technology"},
    )

    out = get_peer_comparables_yfinance("AAPL", "2026-01-15")
    assert "Valuation Multiples" in out
    assert "Trailing P/E" in out


def test_fmp_revision_note_detects_eps_up():
    from tradingagents.dataflows.fmp_estimates import _revision_note

    latest = {"epsAvg": 2.2, "revenueAvg": 100.0}
    prior = {"epsAvg": 2.0, "revenueAvg": 95.0}
    lines = _revision_note(latest, prior)
    joined = "\n".join(lines)
    assert "EPS avg" in joined
    assert "up" in joined.lower()
