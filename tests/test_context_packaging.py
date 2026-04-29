"""Tests for LLM context truncation and analyst evidence digest."""

from copy import deepcopy

import pytest

from tradingagents.agents.utils.agent_utils import (
    build_analyst_evidence_digest,
    get_debate_context_reports,
    truncate_report_for_prompt,
)
from tradingagents.default_config import DEFAULT_CONFIG


def test_truncate_report_unlimited():
    s = "a" * 500
    assert truncate_report_for_prompt(s, None) == s
    assert truncate_report_for_prompt(s, 0) == s


def test_truncate_report_caps():
    s = "hello world"
    out = truncate_report_for_prompt(s, 5)
    assert out.startswith("hello")
    assert "truncated" in out


def test_get_debate_context_reports_respects_cap(monkeypatch):
    cfg = deepcopy(DEFAULT_CONFIG)
    cfg["max_chars_per_report_in_debate"] = 4
    monkeypatch.setattr(
        "tradingagents.dataflows.config.get_config",
        lambda: cfg,
    )
    state = {
        "market_report": "abcde",
        "sentiment_report": "",
        "news_report": "x",
        "fundamentals_report": "yy",
        "forward_report": "zzz",
    }
    m, s, n, f, fwd = get_debate_context_reports(state)
    assert m == "abcd\n… [truncated, 5 total chars]"
    assert s == ""
    assert n == "x"
    assert f == "yy"
    assert fwd == "zzz"


def test_build_analyst_evidence_digest_empty_and_excerpt(monkeypatch):
    cfg = deepcopy(DEFAULT_CONFIG)
    cfg["analyst_evidence_digest_max_chars_per_report"] = 6
    monkeypatch.setattr(
        "tradingagents.dataflows.config.get_config",
        lambda: cfg,
    )
    state = {
        "market_report": "123456789",
        "sentiment_report": "",
        "news_report": "hi",
        "fundamentals_report": "",
        "forward_report": "fwd",
    }
    digest = build_analyst_evidence_digest(state)
    assert "### Market" in digest
    assert "123456" in digest
    assert "truncated" in digest
    assert "no report" in digest
    assert "hi" in digest
