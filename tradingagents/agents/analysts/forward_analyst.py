from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_analyst_estimates,
    get_language_instruction,
    get_macro_regime,
    get_news,
    get_options_implied_move,
    get_peer_comparables,
    get_sector_etf_trends,
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
        ]

        system_message = (
            """You are the Forward Analyst. Build a probability-weighted future outlook that integrates consensus estimates, macro regime, peer/sector context, and scenario stress testing.

Required process:
1) Call `get_analyst_estimates` first.
2) Call `get_peer_comparables` and `get_macro_regime`.
3) Call `get_sector_etf_trends` using the most relevant sector/ETF implied by your findings.
4) Optionally call `get_options_implied_move` for event-volatility context.
5) Use `get_news` for corroboration of forward catalysts and risks.

Scenario playbook (must use):
"""
            + get_all_scenarios_text()
            + """

Required report sections (use these exact headings):
## Executive Summary
## Sector and Secular Theme Classification
## Consensus Expectations and Estimate Drift
## Peer and Sector Relative Positioning
## Macro Regime Alignment
## Event Risk and Implied Volatility Context
## Bull, Base, Bear Scenario Framework
## Probability-Weighted 12M and 36M Target Ranges
## Catalyst Watchlist
## Thesis Invalidation Conditions
## Actionable Implications for Research and Portfolio Teams

Rubric:
- Name at least two secular themes and explain mechanism, not slogans.
- Provide explicit bull/base/bear probabilities with assumptions.
- Include both upside pathways and failure pathways.
- Separate what is consensus from what is non-consensus.
- Be specific about what evidence would cause probability updates.

Finish with a Markdown table named "Forward Scenario Evidence Table" with scenario, assumptions, probability, expected impact, and update trigger."""
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
