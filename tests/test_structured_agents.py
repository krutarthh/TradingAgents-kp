"""Tests for structured-output agents (Trader and Research Manager).

The Portfolio Manager has its own coverage in tests/test_memory_log.py
(which exercises the full memory-log → PM injection cycle).  This file
covers the parallel schemas, render functions, and graceful-fallback
behavior we added for the Trader and Research Manager so all three
decision-making agents share the same shape.
"""

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.schemas import (
    PortfolioDecision,
    PortfolioRating,
    ResearchPlan,
    TraderAction,
    TraderProposal,
    render_research_plan,
    render_trader_proposal,
)
from tradingagents.agents.trader.trader import create_trader


# ---------------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderTraderProposal:
    def test_minimal_required_fields(self):
        p = TraderProposal(action=TraderAction.HOLD, reasoning="Balanced setup; no edge.")
        md = render_trader_proposal(p)
        assert "**Action**: Hold" in md
        assert "**Reasoning**: Balanced setup; no edge." in md
        # The trailing FINAL TRANSACTION PROPOSAL line is preserved for the
        # analyst stop-signal text and any external code that greps for it.
        assert "FINAL TRANSACTION PROPOSAL: **HOLD**" in md

    def test_optional_fields_included_when_present(self):
        p = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Strong technicals + fundamentals.",
            entry_price=189.5,
            stop_loss=178.0,
            position_sizing="6% of portfolio",
        )
        md = render_trader_proposal(p)
        assert "**Action**: Buy" in md
        assert "**Entry Price**: 189.5" in md
        assert "**Stop Loss**: 178.0" in md
        assert "**Position Sizing**: 6% of portfolio" in md
        assert "FINAL TRANSACTION PROPOSAL: **BUY**" in md

    def test_optional_fields_omitted_when_absent(self):
        p = TraderProposal(action=TraderAction.SELL, reasoning="Guidance cut.")
        md = render_trader_proposal(p)
        assert "Entry Price" not in md
        assert "Stop Loss" not in md
        assert "Position Sizing" not in md
        assert "FINAL TRANSACTION PROPOSAL: **SELL**" in md


@pytest.mark.unit
class TestRenderResearchPlan:
    def test_required_fields(self):
        p = ResearchPlan(
            recommendation=PortfolioRating.OVERWEIGHT,
            rationale="Bull case carried; tailwinds intact.",
            strategic_actions="Build position over two weeks; cap at 5%.",
        )
        md = render_research_plan(p)
        assert "**Recommendation**: Overweight" in md
        assert "**Rationale**: Bull case carried" in md
        assert "**Strategic Actions**: Build position" in md

    def test_all_5_tier_ratings_render(self):
        for rating in PortfolioRating:
            p = ResearchPlan(
                recommendation=rating,
                rationale="r",
                strategic_actions="s",
            )
            md = render_research_plan(p)
            assert f"**Recommendation**: {rating.value}" in md

    def test_extended_fields_render_when_present(self):
        p = ResearchPlan(
            recommendation=PortfolioRating.BUY,
            rationale="Thesis improving.",
            strategic_actions="Scale over two tranches.",
            secular_themes=["AI capex", "reshoring"],
            key_catalysts=["earnings beat", "guidance raise"],
            key_risks=["capex slowdown"],
            multi_horizon_view="0-6w constructive; 12m positive; 36m high upside with volatility.",
        )
        md = render_research_plan(p)
        assert "**Secular Themes**: AI capex, reshoring" in md
        assert "**Key Catalysts**: earnings beat, guidance raise" in md
        assert "**Key Risks**: capex slowdown" in md
        assert "**Multi-Horizon View**:" in md


@pytest.mark.unit
class TestPortfolioDecisionSchema:
    def test_probability_sum_validator_accepts_one(self):
        decision = PortfolioDecision(
            rating=PortfolioRating.OVERWEIGHT,
            executive_summary="Summary.",
            investment_thesis="Thesis.",
            bull_probability=0.3,
            base_probability=0.5,
            bear_probability=0.2,
        )
        assert decision.base_probability == 0.5

    def test_probability_sum_validator_rejects_invalid_sum(self):
        with pytest.raises(ValueError):
            PortfolioDecision(
                rating=PortfolioRating.HOLD,
                executive_summary="Summary.",
                investment_thesis="Thesis.",
                bull_probability=0.6,
                base_probability=0.3,
                bear_probability=0.3,
            )


# ---------------------------------------------------------------------------
# Trader agent: structured happy path + fallback
# ---------------------------------------------------------------------------


def _make_trader_state():
    return {
        "company_of_interest": "NVDA",
        "investment_plan": "**Recommendation**: Buy\n**Rationale**: ...\n**Strategic Actions**: ...",
        "forward_report": "Forward scenarios include AI_CAPEX_ACCELERATION and RATE_CUT_CYCLE.",
    }


def _structured_trader_llm(captured: dict, proposal: TraderProposal | None = None):
    """Build a MagicMock LLM whose with_structured_output binding captures the
    prompt and returns a real TraderProposal so render_trader_proposal works.
    """
    if proposal is None:
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Strong setup.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or proposal
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestTraderAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="AI capex cycle intact; institutional flows constructive.",
            entry_price=189.5,
            stop_loss=178.0,
            position_sizing="6% of portfolio",
        )
        llm = _structured_trader_llm(captured, proposal)
        trader = create_trader(llm)
        result = trader(_make_trader_state())
        plan = result["trader_investment_plan"]
        assert "**Action**: Buy" in plan
        assert "**Entry Price**: 189.5" in plan
        assert "FINAL TRANSACTION PROPOSAL: **BUY**" in plan
        # The same rendered markdown is also added to messages for downstream agents.
        assert plan in result["messages"][0].content

    def test_prompt_includes_investment_plan(self):
        captured = {}
        llm = _structured_trader_llm(captured)
        trader = create_trader(llm)
        trader(_make_trader_state())
        # The investment plan is in the user message of the captured prompt.
        prompt = captured["prompt"]
        assert any("Proposed Investment Plan" in m["content"] for m in prompt)
        assert any("Forward Scenarios and Secular Outlook" in m["content"] for m in prompt)

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain_response = (
            "**Action**: Sell\n\nGuidance cut hits margins.\n\n"
            "FINAL TRANSACTION PROPOSAL: **SELL**"
        )
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain_response)
        trader = create_trader(llm)
        result = trader(_make_trader_state())
        assert result["trader_investment_plan"] == plain_response


# ---------------------------------------------------------------------------
# Research Manager agent: structured happy path + fallback
# ---------------------------------------------------------------------------


def _make_rm_state():
    return {
        "company_of_interest": "NVDA",
        "forward_report": "Forward report with bull/base/bear scenarios.",
        "integrated_thesis_report": "INTEGRATED_THESIS_SENTINEL",
        "verification_notes": "VERIFICATION_SENTINEL",
        "investment_debate_state": {
            "history": "Bull and bear arguments here.",
            "bull_history": "Bull says...",
            "bear_history": "Bear says...",
            "current_response": "",
            "judge_decision": "",
            "count": 1,
        },
    }


def _structured_rm_llm(captured: dict, plan: ResearchPlan | None = None):
    if plan is None:
        plan = ResearchPlan(
            recommendation=PortfolioRating.HOLD,
            rationale="Balanced view across both sides.",
            strategic_actions="Hold current position; reassess after earnings.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or plan
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestResearchManagerAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        plan = ResearchPlan(
            recommendation=PortfolioRating.OVERWEIGHT,
            rationale="Bull case is stronger; AI tailwind intact.",
            strategic_actions="Build position gradually over two weeks.",
        )
        llm = _structured_rm_llm(captured, plan)
        rm = create_research_manager(llm)
        result = rm(_make_rm_state())
        ip = result["investment_plan"]
        assert "**Recommendation**: Overweight" in ip
        assert "**Rationale**: Bull case" in ip
        assert "**Strategic Actions**: Build position" in ip

    def test_prompt_uses_5_tier_rating_scale(self):
        """The RM prompt must list all five tiers so the schema enum matches user expectations."""
        captured = {}
        llm = _structured_rm_llm(captured)
        rm = create_research_manager(llm)
        rm(_make_rm_state())
        prompt = captured["prompt"]
        for tier in ("Buy", "Overweight", "Hold", "Underweight", "Sell"):
            assert f"**{tier}**" in prompt, f"missing {tier} in prompt"
        assert "Forward Scenarios Report" in prompt

    def test_prompt_includes_integrated_thesis_and_verification_notes(self):
        captured = {}
        llm = _structured_rm_llm(captured)
        rm = create_research_manager(llm)
        rm(_make_rm_state())
        prompt = captured["prompt"]
        assert "INTEGRATED_THESIS_SENTINEL" in prompt
        assert "VERIFICATION_SENTINEL" in prompt

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain_response = "**Recommendation**: Sell\n\n**Rationale**: ...\n\n**Strategic Actions**: ..."
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain_response)
        rm = create_research_manager(llm)
        result = rm(_make_rm_state())
        assert result["investment_plan"] == plain_response


@pytest.mark.unit
class TestForwardReportPlumbingInPrompts:
    def test_bull_bear_and_risk_prompts_include_forward_report(self):
        base_state = {
            "investment_debate_state": {
                "history": "Debate history.",
                "bull_history": "",
                "bear_history": "",
                "current_response": "Counterpoint",
                "judge_decision": "",
                "count": 1,
            },
            "risk_debate_state": {
                "history": "Risk history.",
                "aggressive_history": "",
                "conservative_history": "",
                "neutral_history": "",
                "latest_speaker": "Aggressive",
                "current_aggressive_response": "Aggressive view",
                "current_conservative_response": "Conservative view",
                "current_neutral_response": "Neutral view",
                "judge_decision": "",
                "count": 1,
            },
            "market_report": "market",
            "sentiment_report": "sentiment",
            "news_report": "news",
            "fundamentals_report": "fundamentals",
            "forward_report": "FORWARD_REPORT_SENTINEL",
            "integrated_thesis_report": "INTEGRATED_THESIS_SENTINEL",
            "trader_investment_plan": "Trader plan",
        }

        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content="ok")

        create_bull_researcher(llm)(base_state)
        assert "FORWARD_REPORT_SENTINEL" in llm.invoke.call_args_list[-1].args[0]
        assert "INTEGRATED_THESIS_SENTINEL" in llm.invoke.call_args_list[-1].args[0]

        create_bear_researcher(llm)(base_state)
        assert "FORWARD_REPORT_SENTINEL" in llm.invoke.call_args_list[-1].args[0]
        assert "INTEGRATED_THESIS_SENTINEL" in llm.invoke.call_args_list[-1].args[0]

        create_aggressive_debator(llm)(base_state)
        assert "FORWARD_REPORT_SENTINEL" in llm.invoke.call_args_list[-1].args[0]

        create_conservative_debator(llm)(base_state)
        assert "FORWARD_REPORT_SENTINEL" in llm.invoke.call_args_list[-1].args[0]

        create_neutral_debator(llm)(base_state)
        assert "FORWARD_REPORT_SENTINEL" in llm.invoke.call_args_list[-1].args[0]

    def test_portfolio_manager_prompt_includes_forward_report(self):
        captured = {}
        decision = PortfolioDecision(
            rating=PortfolioRating.HOLD,
            executive_summary="Summary.",
            investment_thesis="Thesis.",
        )
        structured = MagicMock()
        structured.invoke.side_effect = lambda prompt: (
            captured.__setitem__("prompt", prompt) or decision
        )
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        pm = create_portfolio_manager(llm)

        state = {
            "company_of_interest": "NVDA",
            "risk_debate_state": {
                "history": "Risk debate history",
                "aggressive_history": "",
                "conservative_history": "",
                "neutral_history": "",
                "latest_speaker": "Neutral",
                "current_aggressive_response": "",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "judge_decision": "",
                "count": 3,
            },
            "investment_plan": "Investment plan",
            "trader_investment_plan": "Trader plan",
            "forward_report": "FORWARD_REPORT_SENTINEL",
            "past_context": "",
        }

        pm(state)
        assert "FORWARD_REPORT_SENTINEL" in captured["prompt"]
