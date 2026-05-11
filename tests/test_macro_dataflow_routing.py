"""Tests for FRED / yfinance macro routing."""

from unittest.mock import patch

import pytest

from tradingagents.dataflows.config import DataVendorSkipped


def test_macro_regime_routed_fails_without_fred():
    from tradingagents.dataflows import interface

    with patch.object(
        interface,
        "get_macro_regime_fred",
        side_effect=DataVendorSkipped("no key"),
    ):
        with pytest.raises(DataVendorSkipped):
            interface.get_macro_regime_routed("2024-01-15")


def test_macro_regime_routed_combines_fred_and_complement():
    from tradingagents.dataflows import interface

    with patch.object(interface, "get_macro_regime_fred", return_value="FRED_BLOCK"):
        with patch.object(
            interface,
            "get_macro_regime_yfinance_complement",
            return_value="YF_COMP",
        ):
            out = interface.get_macro_regime_routed("2024-01-15")
            assert out == "FRED_BLOCK\n\nYF_COMP"


def test_get_macro_regime_fred_skips_without_key(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    from tradingagents.dataflows.fred_macro import get_macro_regime_fred

    with pytest.raises(DataVendorSkipped):
        get_macro_regime_fred("2024-01-15")


def test_get_sec_filing_highlights_skips_without_ninjas_key(monkeypatch):
    monkeypatch.delenv("API_NINJA_API_KEY", raising=False)
    monkeypatch.delenv("API_NINJAS_API_KEY", raising=False)
    from tradingagents.dataflows.api_ninjas_sec import get_sec_filing_highlights_ninjas

    with pytest.raises(DataVendorSkipped):
        # Underlying fetch raises DataVendorSkipped when key is missing.
        get_sec_filing_highlights_ninjas("AAPL", "2024-01-15")


def test_route_to_vendor_sec_filings_hard_fails_when_key_missing(monkeypatch):
    from tradingagents.dataflows import interface

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "api_ninjas")
    with patch.object(
        interface,
        "get_sec_filing_highlights_ninjas",
        side_effect=DataVendorSkipped("no key"),
    ):
        # Ensure VENDOR_METHODS reflects patched symbol.
        monkeypatch.setitem(
            interface.VENDOR_METHODS["get_sec_filing_highlights"],
            "api_ninjas",
            interface.get_sec_filing_highlights_ninjas,
        )
        with pytest.raises(RuntimeError, match="All configured vendors failed"):
            interface.route_to_vendor("get_sec_filing_highlights", "SHOP", "2026-01-15")


def test_route_to_vendor_sec_filings_prefers_api_ninjas_when_available(monkeypatch):
    from tradingagents.dataflows import interface

    monkeypatch.setattr(
        interface,
        "get_vendor",
        lambda category, method=None: "api_ninjas",
    )
    with patch.object(interface, "get_sec_filing_highlights_ninjas", return_value="NINJAS_OK"):
        monkeypatch.setitem(
            interface.VENDOR_METHODS["get_sec_filing_highlights"],
            "api_ninjas",
            interface.get_sec_filing_highlights_ninjas,
        )
        out = interface.route_to_vendor("get_sec_filing_highlights", "SHOP", "2026-01-15")
        assert "NINJAS_OK" in out
        assert "[vendor=api_ninjas]" in out
