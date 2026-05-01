from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_analyst_estimates,
    get_earnings_transcript_highlights,
    get_language_instruction,
    get_macro_regime,
    get_news,
    get_options_implied_move,
    get_peer_comparables,
    probability_weighted_price,
    get_sec_filing_highlights,
    get_sec_filing_sections,
    get_sector_etf_trends,
)
from tradingagents.agents.utils.analysis_framework import get_analysis_contract_suffix
from tradingagents.agents.utils.calculator_tool import (
    evaluate_math_expression,
    implied_cagr,
    valuation_sensitivity_table,
)
from tradingagents.agents.utils.scenarios import get_all_scenarios_text


def create_forward_analyst(llm):
    def forward_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)

        tools = [
            get_analyst_estimates,
            get_peer_comparables,
            get_macro_regime,
            get_sector_etf_trends,
            get_options_implied_move,
            get_news,
            get_sec_filing_highlights,
            get_sec_filing_sections,
            get_earnings_transcript_highlights,
            evaluate_math_expression,
            implied_cagr,
            probability_weighted_price,
            valuation_sensitivity_table,
        ]

        system_message = (
            """You are the Forward Analyst. Build a probability-weighted future outlook that integrates consensus estimates, macro regime, peer/sector context, and scenario stress testing.

Required process:
1) Call `get_analyst_estimates` first.
2) Call `get_peer_comparables` and `get_macro_regime`.
3) Call `get_sector_etf_trends` using the most relevant sector/ETF implied by your findings.
4) Optionally call `get_options_implied_move` for event-volatility context.
5) Use `get_sec_filing_highlights` (10-K) to ground medium-term strategic assumptions in primary filing cadence.
6) Call `get_sec_filing_sections` to fetch filing text from the SEC URL and extract forward-relevant evidence.
7) Read in this order: MD&A -> Financial statements -> Footnotes -> Risk Factors -> Business context.
8) Use `get_earnings_transcript_highlights` when available; if unavailable, state that limitation explicitly.
9) Use `get_news` for corroboration of forward catalysts and risks.
10) Use `evaluate_math_expression` and `implied_cagr` for implied growth, margin, or multiple math—do not rely on mental arithmetic alone.
11) Use `probability_weighted_price` for explicit expected-value price synthesis from bull/base/bear targets.
12) If `enable_valuation_sensitivity_tables` is on, include one `valuation_sensitivity_table` stress block.

Scenario playbook (must use):
"""
            + get_all_scenarios_text()
            + """

Required report sections (use these exact headings):
## Executive Summary
## Sector and Secular Theme Classification
## Consensus Expectations and Estimate Drift
## Peer and Sector Relative Positioning
## Valuation Triangulation (consensus / multiples vs second anchor)
## Macro Regime Alignment
## Event Risk and Implied Volatility Context
## Bull, Base, Bear Scenario Framework
## Probability-Weighted 12M and 36M Target Ranges
## Catalyst Watchlist
## Thesis Invalidation Conditions
## Actionable Implications for Research and Portfolio Teams

Rubric:
- Name at least two secular themes and explain mechanism, not slogans.
- **Valuation**: require two anchors—e.g. peer-relative multiple band from `get_peer_comparables` plus a second check (consensus growth vs history, implied upside from targets, or simple sanity using `evaluate_math_expression`). Do not conclude "cheap" on one multiple alone.
- **SEC filing evidence is mandatory**: include at least one forward-looking claim grounded in the fetched filing URL text (not just the filing metadata row).
- Provide explicit bull/base/bear probabilities that sum to about 1.0 with assumptions.
- Include both upside pathways and failure pathways.
- Separate what is consensus from what is non-consensus.
- Be specific about what evidence would cause probability updates.

Finish with a Markdown table named "Forward Scenario Evidence Table" with scenario, assumptions, probability, expected impact, and update trigger."""
            + get_analysis_contract_suffix()
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "forward_report": report,
        }

    return forward_analyst_node
