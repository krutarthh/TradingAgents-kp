"""Tests for thesis integrator fallback, verifier-plus, and tool metadata banners."""

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
        lambda: {"enable_verification_gate": True, "verification_max_retries": 1},
    )
    gate = create_verification_gate()
    state = {
        "integrated_thesis_report": """## Unified thesis
bull/base/bear

## Cross-sectional facts (market vs sector vs benchmark)
- Instrument RS vs SPY inline with sector ETF (Market + Forward).

## Assumptions table
| a | b | c |

## Cross-report conflicts
- none

## Valuation non-negotiables
- peers

## Catalysts and repricing
- earnings
""",
        "forward_report": "## Executive Summary\n## Valuation Triangulation\nEvidence: model\nbull 30% base 40% bear 30%",
        "market_report": "## Benchmark-Relative Dashboard\n| Lens | Metric | NVDA | SPY | XLK | Lead |\n| --- | --- | --- | --- | --- | --- |\n## Executive Summary\nMarket regime trend continuation.",
        "sentiment_report": "## Executive Summary\nSocial sentiment neutral.",
        "news_report": "## Executive Summary\nMacro liquidity and rates stable.",
        "fundamentals_report": "## Executive Summary\n## Valuation Triangulation\nFree cash flow supports multiples.",
        "verification_attempts": 0,
    }
    out = gate(state)
    assert out["verification_status"] == "pass"
    assert "OK" in out["verification_notes"]


@pytest.mark.unit
def test_verification_gate_fail_then_warn_after_retry_limit(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.managers.verification_gate.get_config",
        lambda: {"enable_verification_gate": True, "verification_max_retries": 1},
    )
    gate = create_verification_gate()
    failing_state = {
        "integrated_thesis_report": "## Unified thesis\nmissing key sections",
        "forward_report": "## Executive Summary\nwith numbers 15%",
        "market_report": "## Executive Summary\nwith numbers 22%",
        "fundamentals_report": "## Executive Summary\nwith numbers 10%",
        "verification_attempts": 0,
    }
    out1 = gate(failing_state)
    assert out1["verification_status"] == "fail"

    failing_state["verification_attempts"] = 1
    out2 = gate(failing_state)
    assert out2["verification_status"] == "warn"


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
    assert "## Cross-sectional facts" in text
    assert "## Cross-report conflicts" in text
    assert "## Valuation non-negotiables" in text
