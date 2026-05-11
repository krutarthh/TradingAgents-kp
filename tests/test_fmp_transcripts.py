"""Unit tests for Financial Modeling Prep transcript helpers."""

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows.config import DataVendorSkipped
from tradingagents.dataflows.fmp_transcripts import (
    _pick_latest_quarter_before_anchor,
    get_earnings_transcript_highlights_fmp,
)


@pytest.mark.unit
def test_pick_latest_quarter_before_anchor():
    from datetime import datetime

    rows = [
        {"year": 2024, "quarter": 1, "date": "2024-02-01"},
        {"year": 2023, "quarter": 4, "date": "2023-11-02"},
    ]
    anchor = datetime.strptime("2024-06-01", "%Y-%m-%d")
    picked = _pick_latest_quarter_before_anchor(rows, anchor)
    assert picked == {"year": 2024, "quarter": 1, "date": "2024-02-01"}


@pytest.mark.unit
def test_get_fmp_transcript_skips_without_api_key(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.delenv("FINANCIAL_MODELING_PREP_API_KEY", raising=False)
    with pytest.raises(DataVendorSkipped, match="FMP_API_KEY"):
        get_earnings_transcript_highlights_fmp("AAPL", "2024-06-01")


@pytest.mark.unit
def test_get_fmp_transcript_formats_excerpt(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test-key")

    dates_payload = [{"year": 2024, "quarter": 1, "date": "2024-02-01"}]
    transcript_payload = [{"speaker": "CEO", "content": "Revenue grew."}]

    def fake_get(url, params=None, timeout=None):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        if "transcript-dates" in url:
            mock_resp.json.return_value = dates_payload
        elif "earning-call-transcript" in url:
            mock_resp.json.return_value = transcript_payload
        else:
            mock_resp.json.return_value = []
        return mock_resp

    with patch("tradingagents.dataflows.fmp_transcripts.requests.get", side_effect=fake_get):
        with patch("tradingagents.dataflows.fmp_transcripts.cache_get_json", return_value=None):
            with patch("tradingagents.dataflows.fmp_transcripts.cache_set_json"):
                body = get_earnings_transcript_highlights_fmp("AAPL", "2024-06-01")

    assert "CEO" in body
    assert "Revenue grew" in body
    assert "Financial Modeling Prep" in body
