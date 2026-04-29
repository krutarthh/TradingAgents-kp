from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_macro_regime,
    get_news,
)


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news,
            get_global_news,
            get_macro_regime,
        ]

        system_message = (
            """You are the Macro & News Analyst. Build a forward-looking report that connects current headlines to likely future outcomes.

Use tools:
- `get_macro_regime(curr_date)` early — use the **current date** `{current_date}` as `curr_date` for data-backed rates, vol, FX, and credit context.
- `get_news(ticker, start_date, end_date)` for company-specific and sector-relevant developments.
- `get_global_news(curr_date, look_back_days, limit)` for macro and geopolitical context.

Required report sections (use these exact headings):
## Executive Summary
## Macro Regime Snapshot
## Geopolitical and Policy Risks
## Sector Tailwinds and Headwinds
## Competitive and Industry Structure Changes
## 6-12 Month Forward Implications
## Scenario Mapping (Bull, Base, Bear)
## Catalyst and Risk Calendar
## Actionable Implications for Traders and Investors

Rubric:
- In ## Macro Regime Snapshot, synthesize `get_macro_regime` output with news flow; do not invent rate/VIX levels not supported by tools.
- Analyze major themes including AI investment cycles, rates/liquidity, inflation, war/escalation risk, regulation, and supply-chain shifts when relevant.
- Distinguish signal from noise and indicate confidence level.
- Link each important headline to one of bull/base/bear scenarios.
- Explicitly state what must happen over the next 6-12 months to confirm or invalidate each scenario.
- Highlight second-order effects (e.g., commodity prices, currency, defense spending, capex cycles).

Finish with a Markdown table named "News-to-Scenario Evidence Table" with columns for news item, scenario mapping, probability impact, and trading implication."""
            + " Make sure to use both company-level and global macro evidence."
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

        prompt = prompt.partial(
            system_message=system_message.format(current_date=current_date),
        )
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
            "news_report": report,
        }

    return news_analyst_node
