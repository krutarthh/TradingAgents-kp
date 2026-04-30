"""Tests for thesis integrator fallback, verifier-lite, and tool metadata banners."""

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.thesis_integrator import create_thesis_integrator
from tradingagents.agents.managers.verification_gate import create_verification_gate
from tradingagents.dataflows.tool_response_metadata import prefix_string_body


@pytest.mark.unit
def test_prefix_string_body_adds_banner():
    out = prefix_string_body(
        "get_fundamentals",
        "yfinance",
        "OK",
        ("NVDA",),
        {"curr_date": "2026-01-01"},
    )
    assert "[tool=get_fundamentals]" in out
    assert "[vendor=yfinance]" in out
    assert "[symbol=NVDA]" in out
    assert "[as_of=2026-01-01]" in out
    assert out.endswith("OK")


@pytest.mark.unit
def test_verification_gate_ok_with_full_integrated_thesis(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.managers.verification_gate.get_config",
        lambda: {"enable_verification_gate": True},
    )
    gate = create_verification_gate()
    state = {
        "integrated_thesis_report": """## Unified thesis
bull/base/bear

## Assumptions table
| a | b | c |

## Cross-report conflicts
- none

## Valuation non-negotiables
- peers

## Catalysts and repricing
- earnings
""",
        "forward_report": "## Executive Summary\nbull 30% base 40% bear 30%",
        "market_report": "## Executive Summary\nok",
        "fundamentals_report": "## Executive Summary\nok",
    }
    out = gate(state)
    assert "OK" in out["verification_notes"]


@pytest.mark.unit
def test_thesis_integrator_digest_fallback_has_required_headings(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.managers.thesis_integrator.get_config",
        lambda: {"enable_thesis_integrator": False},
    )
    node = create_thesis_integrator(MagicMock())
    state = {
        "company_of_interest": "NVDA",
        "trade_date": "2026-01-01",
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "forward_report": "",
    }
    result = node(state)
    text = result["integrated_thesis_report"]
    assert "## Unified thesis" in text
    assert "Thesis integrator LLM disabled" in text
    assert "## Cross-report conflicts" in text
    assert "## Valuation non-negotiables" in text
