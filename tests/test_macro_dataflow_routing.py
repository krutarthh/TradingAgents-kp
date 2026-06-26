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


def test_route_to_vendor_sec_filings_returns_skip_message_when_key_missing(monkeypatch):
    from tradingagents.dataflows import interface

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "api_ninjas")
    with patch.object(
        interface,
        "get_sec_filing_highlights_ninjas",
        side_effect=DataVendorSkipped("no key"),
    ):
        monkeypatch.setitem(
            interface.VENDOR_METHODS["get_sec_filing_highlights"],
            "api_ninjas",
            interface.get_sec_filing_highlights_ninjas,
        )
        out = interface.route_to_vendor("get_sec_filing_highlights", "SHOP", "2026-01-15")
        assert "no key" in out
        assert "[vendor=api_ninjas]" in out


def test_sec_ticker_candidates_goog_prefers_googl():
    from tradingagents.dataflows.api_ninjas_sec import _sec_ticker_candidates

    assert _sec_ticker_candidates("GOOG") == ["GOOGL", "GOOG"]


def test_fetch_sec_filings_retries_googl_when_goog_returns_400(monkeypatch):
    import requests

    from tradingagents.dataflows.api_ninjas_sec import _fetch_sec_filings

    monkeypatch.setenv("API_NINJA_API_KEY", "test-key")
    calls: list[str] = []

    def fake_get(url, params, headers, timeout):
        calls.append(params["ticker"])

        class Resp:
            status_code = 400 if params["ticker"] == "GOOG" else 200

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise requests.HTTPError(response=self)

            def json(self):
                return [{"ticker": "GOOGL", "filing_date": "2024-01-01", "form_type": "10-K"}]

        return Resp()

    monkeypatch.setattr("tradingagents.dataflows.api_ninjas_sec.requests.get", fake_get)
    rows = _fetch_sec_filings("GOOG", "10-K")
    assert calls == ["GOOGL"]
    assert rows[0]["ticker"] == "GOOGL"


def test_fetch_sec_filings_raises_skip_when_all_candidates_fail(monkeypatch):
    from tradingagents.dataflows.api_ninjas_sec import _fetch_sec_filings

    monkeypatch.setenv("API_NINJA_API_KEY", "test-key")

    class Resp:
        status_code = 400

    monkeypatch.setattr(
        "tradingagents.dataflows.api_ninjas_sec.requests.get",
        lambda *args, **kwargs: Resp(),
    )

    with pytest.raises(DataVendorSkipped, match="tried"):
        _fetch_sec_filings("GOOG", "10-K")


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
