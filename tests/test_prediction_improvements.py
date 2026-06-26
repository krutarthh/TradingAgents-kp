"""Tests for the prediction-quality improvements.

Covers the new eval metrics, rich signal extraction, directional calibration,
adaptive debate depth, verifier numeric reconciliation, the empty-report guard,
and the new data connectors' strict-temporal / form-handling behavior.
"""

import pytest

from tradingagents.evaluation import metrics
from tradingagents.agents.utils import decision_signal
from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
from tradingagents.agents.utils.rating import parse_rating_with_status, rating_bucket
from tradingagents.graph.conditional_logic import ConditionalLogic


# ---------------------------------------------------------------------------
# Eval metrics
# ---------------------------------------------------------------------------

_ROWS = [
    {"rating": "Buy", "rating_bucket": "bullish", "alpha_return_365d": 0.10, "raw_return_365d": 0.15},
    {"rating": "Sell", "rating_bucket": "bearish", "alpha_return_365d": -0.20, "raw_return_365d": -0.10},
    {"rating": "Hold", "rating_bucket": "neutral", "alpha_return_365d": 0.01, "raw_return_365d": 0.02},
    {"rating": "Buy", "rating_bucket": "bullish", "alpha_return_365d": -0.05, "raw_return_365d": 0.00},
]


@pytest.mark.unit
class TestMetrics:
    def test_directional_accuracy_and_long_short(self):
        block = metrics.horizon_metrics(_ROWS, 365, n_boot=0)
        assert block["n_scored"] == 4
        # Buy/+0.10 ok, Sell/-0.20 ok, Hold/0.01 within band ok, Buy/-0.05 wrong.
        assert block["directional_accuracy"] == pytest.approx(0.75)
        # signed alpha: +0.10, +0.20, 0, -0.05 -> mean 0.0625
        assert block["long_short_alpha"] == pytest.approx(0.0625)

    def test_confusion_matrix_counts(self):
        block = metrics.horizon_metrics(_ROWS, 365, n_boot=0)
        cm = block["confusion_matrix"]
        # Two bullish predictions: realized bullish (0.10) and neutral (-0.05 in band)
        assert cm["bullish"]["bullish"] == 1
        assert cm["bullish"]["neutral"] == 1
        assert cm["bearish"]["bearish"] == 1
        assert cm["neutral"]["neutral"] == 1

    def test_baselines_present(self):
        block = metrics.horizon_metrics(_ROWS, 365, n_boot=0)
        baselines = block["baselines"]
        assert "always_long" in baselines
        assert baselines["random"]["long_short_alpha"] == 0.0
        # No momentum/consensus columns -> reported unavailable, not silently 0.
        assert baselines["momentum"]["available"] is False

    def test_bootstrap_ci_present_when_requested(self):
        block = metrics.horizon_metrics(_ROWS, 365, n_boot=200, seed=1)
        assert "directional_accuracy_ci95" in block
        lo, hi = block["directional_accuracy_ci95"]
        assert 0.0 <= lo <= hi <= 1.0

    def test_calibration_with_probabilities(self):
        rows = [
            {"rating_bucket": "bullish", "alpha_return_365d": 0.2,
             "bull_probability": 0.7, "base_probability": 0.2, "bear_probability": 0.1},
            {"rating_bucket": "bearish", "alpha_return_365d": -0.2,
             "bull_probability": 0.1, "base_probability": 0.2, "bear_probability": 0.7},
        ]
        block = metrics.horizon_metrics(rows, 365, n_boot=0)
        calib = block["calibration"]
        assert calib["available"] is True
        assert calib["multiclass_brier"] is not None

    def test_summarize_tracks_parse_failures_and_fallbacks(self):
        rows = [
            {"rating": "Buy", "rating_bucket": "bullish", "alpha_return_365d": 0.1,
             "rating_parse_failed": "true", "structured_fallback_used": "true"},
        ]
        summary = metrics.summarize_predictions(rows, [365], n_boot=0)
        assert summary["n_rating_parse_failures"] == 1
        assert summary["n_structured_fallbacks"] == 1
        assert "365" in summary["horizons"]
        assert "anchors" in summary  # backward-compatible block retained


# ---------------------------------------------------------------------------
# Rich signal extraction + reconciliation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDecisionSignal:
    def test_signal_from_decision(self):
        d = PortfolioDecision(
            rating=PortfolioRating.BUY,
            executive_summary="Build.",
            investment_thesis="Strong.",
            bull_probability=0.6,
            base_probability=0.3,
            bear_probability=0.1,
            price_target=215.0,
        )
        sig = decision_signal.signal_from_decision(d)
        assert sig["rating"] == "Buy"
        assert sig["rating_bucket"] == "bullish"
        assert sig["rating_score"] == 2
        assert sig["directional_score"] == pytest.approx(0.5)
        assert sig["confidence"] == pytest.approx(0.6)
        assert sig["rating_parse_failed"] is False

    def test_signal_from_markdown_flags_parse_failure(self):
        sig = decision_signal.signal_from_markdown("No directional call here.")
        assert sig["rating_parse_failed"] is True
        assert sig["rating_bucket"] == "unparsed"
        assert sig["structured_fallback_used"] is True

    def test_signal_from_markdown_parses_probs(self):
        md = (
            "**Rating**: Overweight\n\n"
            "**Price Target**: 215.0\n\n"
            "**Scenario Probabilities**: Bull=0.50, Base=0.30, Bear=0.20"
        )
        sig = decision_signal.signal_from_markdown(md)
        assert sig["rating"] == "Overweight"
        assert sig["rating_parse_failed"] is False
        assert sig["bull_probability"] == pytest.approx(0.50)
        assert sig["directional_score"] == pytest.approx(0.30)
        assert sig["price_target"] == pytest.approx(215.0)

    def test_reconcile_trader_pm(self):
        assert decision_signal.reconcile_trader_pm("Buy", "bullish") == "consistent"
        assert decision_signal.reconcile_trader_pm("Sell", "bullish") == "inconsistent"
        assert decision_signal.reconcile_trader_pm("Hold", "bullish") == "divergent"
        assert decision_signal.reconcile_trader_pm(None, "bullish") == "unknown"

    def test_extract_trader_action(self):
        md = "**Action**: Sell\n\n**Reasoning**: exit.\n\nFINAL TRANSACTION PROPOSAL: **SELL**"
        assert decision_signal.extract_trader_action(md) == "Sell"

    def test_parse_rating_with_status(self):
        assert parse_rating_with_status("Rating: Buy") == ("Buy", True)
        assert parse_rating_with_status("nothing here") == (None, False)
        assert rating_bucket("Underweight") == "bearish"


# ---------------------------------------------------------------------------
# Adaptive debate depth
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAdaptiveDebate:
    def _state(self, count, current_response="Bull: still bullish"):
        return {"investment_debate_state": {"count": count, "current_response": current_response}}

    def test_fixed_depth_default(self):
        cl = ConditionalLogic(max_debate_rounds=1)
        assert cl.should_continue_debate(self._state(2)) == "Verification Gate"

    def test_adaptive_extends_when_disagreement(self):
        cl = ConditionalLogic(max_debate_rounds=1, adaptive_debate=True, adaptive_debate_max_rounds=3)
        # Base cap 2 reached, but adaptive cap is 6 and no convergence -> continue.
        assert cl.should_continue_debate(self._state(2)) == "Bear Researcher"

    def test_adaptive_stops_on_convergence(self):
        cl = ConditionalLogic(max_debate_rounds=1, adaptive_debate=True, adaptive_debate_max_rounds=3)
        state = self._state(2, current_response="Bear: I agree, we have reached consensus")
        assert cl.should_continue_debate(state) == "Verification Gate"


# ---------------------------------------------------------------------------
# Verifier numeric reconciliation + empty-report guard
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_verifier_numeric_reconciliation_fails_bad_prob_sum(monkeypatch):
    from tradingagents.agents.managers.verification_gate import create_verification_gate

    monkeypatch.setattr(
        "tradingagents.agents.managers.verification_gate.get_config",
        lambda: {
            "enable_verification_gate": True,
            "verification_max_retries": 1,
            "enable_verifier_numeric_reconciliation": True,
        },
    )
    gate = create_verification_gate()
    state = {
        "integrated_thesis_report": "## Unified thesis\nbull/base/bear\n"
        "## Cross-sectional facts (market vs sector vs benchmark)\n- x\n"
        "## Assumptions table\n| a | b | c |\n"
        "## Cross-report conflicts\n- none\n"
        "## Valuation non-negotiables\n- peers\n"
        "## Catalysts and repricing\n- earnings\n",
        # Bull/base/bear sum to 1.6 -> hard fail under numeric reconciliation.
        "forward_report": "## Executive Summary\n## Valuation Triangulation\nbull 80% base 50% bear 30%",
        "fundamentals_report": "## Executive Summary\n## Valuation Triangulation\nfcf",
        "verification_attempts": 0,
    }
    out = gate(state)
    assert out["verification_status"] == "fail"
    assert out["verification_failed_lane"] == "forward"


@pytest.mark.unit
def test_empty_report_guard_fills_placeholders():
    from tradingagents.agents.managers.thesis_integrator import _guard_empty_reports

    state = {
        "market_report": "real market report",
        "sentiment_report": "",
        "news_report": "   ",
        "fundamentals_report": "real fundamentals",
        "forward_report": "",
    }
    updates = _guard_empty_reports(state)
    assert "sentiment_report" in updates
    assert "news_report" in updates
    assert "forward_report" in updates
    assert "market_report" not in updates  # non-empty untouched
    assert "sentiment" in updates["empty_report_lanes"]


# ---------------------------------------------------------------------------
# Memory directional calibration
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_memory_calibration_is_directional_and_alpha_aware():
    from tradingagents.agents.utils.memory import TradingMemoryLog

    log = TradingMemoryLog(config=None)
    entries = [
        {"rating": "Buy", "alpha": "+5.0%", "raw": "+6.0%"},     # bullish + positive alpha -> win
        {"rating": "Sell", "alpha": "-4.0%", "raw": "-3.0%"},    # bearish + negative alpha -> win
        {"rating": "Buy", "alpha": "-2.0%", "raw": "+1.0%"},     # bullish but negative alpha -> loss
        {"rating": "Hold", "alpha": "+0.5%", "raw": "+0.5%"},    # neutral, small move -> win
    ]
    summary = log._calibration_summary(entries)
    assert "3/4 directionally correct" in summary


# ---------------------------------------------------------------------------
# Connectors: strict-temporal behavior and SEC form handling
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_social_sentiment_skips_in_strict_mode(monkeypatch):
    from tradingagents.dataflows import stocktwits_sentiment

    monkeypatch.setattr(stocktwits_sentiment, "is_strict_temporal", lambda: True)
    out = stocktwits_sentiment.get_social_sentiment_stocktwits("AAPL", "2008-09-15")
    assert "unavailable in strict historical mode" in out


@pytest.mark.unit
def test_options_analytics_skips_in_strict_mode(monkeypatch):
    from tradingagents.dataflows import options_analytics

    monkeypatch.setattr(options_analytics, "is_strict_temporal", lambda: True)
    out = options_analytics.get_options_analytics_yfinance("AAPL", "2008-09-15")
    assert "unavailable in strict historical mode" in out


@pytest.mark.unit
def test_sec_form_normalization():
    from tradingagents.dataflows.api_ninjas_sec import _normalize_form

    assert _normalize_form("10-Q") == "10-Q"
    assert _normalize_form("8-k") == "8-K"
    assert _normalize_form("bogus") == "10-K"
    assert _normalize_form(None) == "10-K"


@pytest.mark.unit
def test_new_methods_routable():
    from tradingagents.dataflows import interface

    for method in (
        "get_social_sentiment",
        "get_ownership_short_interest",
        "get_earnings_calendar",
        "get_options_analytics",
    ):
        # Each new method must belong to a category so route_to_vendor can find it.
        interface.get_category_for_method(method)
