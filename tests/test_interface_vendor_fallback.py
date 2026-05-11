"""Tests for comma-separated vendor failover in route_to_vendor."""

from unittest.mock import patch

import pytest

from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError
from tradingagents.dataflows.api_ninjas_sec import get_earnings_transcript_highlights_stub
from tradingagents.dataflows.config import DataVendorSkipped


def test_route_to_vendor_failover_after_alpha_vantage_rate_limit(monkeypatch):
    import tradingagents.dataflows.interface as interface

    monkeypatch.setattr(
        interface,
        "get_vendor",
        lambda category, method=None: "alpha_vantage,yfinance",
    )

    def restricted(*args, **kwargs):
        raise AlphaVantageRateLimitError("limit")

    monkeypatch.setitem(interface.VENDOR_METHODS["get_stock_data"], "alpha_vantage", restricted)
    monkeypatch.setitem(
        interface.VENDOR_METHODS["get_stock_data"],
        "yfinance",
        lambda *a, **k: "YF_BODY",
    )
    out = interface.route_to_vendor(
        "get_stock_data", "AAPL", "2020-01-01", "2024-06-01"
    )
    assert "YF_BODY" in out
    assert "[vendor=yfinance]" in out


def test_route_to_vendor_transcript_failover_fmp_to_stub(monkeypatch):
    import tradingagents.dataflows.interface as interface

    monkeypatch.setattr(
        interface,
        "get_vendor",
        lambda category, method=None: "financial_modeling_prep,stub",
    )

    def skip(*args, **kwargs):
        raise DataVendorSkipped("no fmp key")

    monkeypatch.setitem(
        interface.VENDOR_METHODS["get_earnings_transcript_highlights"],
        "financial_modeling_prep",
        skip,
    )
    monkeypatch.setitem(
        interface.VENDOR_METHODS["get_earnings_transcript_highlights"],
        "stub",
        get_earnings_transcript_highlights_stub,
    )
    out = interface.route_to_vendor("get_earnings_transcript_highlights", "AAPL", "2024-01-02")
    assert "stub" in out.lower() or "not configured" in out.lower()
    assert "[vendor=stub]" in out


def test_route_to_vendor_requires_vendor_key_on_map(monkeypatch):
    import tradingagents.dataflows.interface as interface

    monkeypatch.setattr(interface, "get_vendor", lambda c, m=None: "nosuch")
    with pytest.raises(RuntimeError, match="All configured vendors failed"):
        interface.route_to_vendor("get_stock_data", "AAPL", "2020-01-01", "2024-06-01")
