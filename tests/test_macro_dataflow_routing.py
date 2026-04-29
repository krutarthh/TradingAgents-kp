"""Tests for FRED / yfinance macro routing."""

from unittest.mock import patch

import pytest

from tradingagents.dataflows.config import DataVendorSkipped


def test_macro_regime_routed_falls_back_without_fred():
    from tradingagents.dataflows import interface

    with patch.object(
        interface,
        "get_macro_regime_fred",
        side_effect=DataVendorSkipped("no key"),
    ):
        with patch.object(
            interface,
            "get_macro_regime_yfinance",
            return_value="YF_FULL",
        ) as yf_full:
            assert interface.get_macro_regime_routed("2024-01-15") == "YF_FULL"
            yf_full.assert_called_once_with("2024-01-15")


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
