from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction, get_news
from tradingagents.agents.utils.analysis_framework import get_analysis_contract_suffix
from tradingagents.dataflows.config import get_config


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news,
        ]

        system_message = (
            """You are the Narrative & Sentiment Analyst. Your mission is to infer market narrative strength and crowd positioning from available news/discussion sources.

Important data caveat:
- You only have access to `get_news(ticker, start_date, end_date)` in this environment.
- Do NOT claim direct scraping of X/Twitter/Reddit/StockTwits.
- Frame sentiment conclusions as a news-driven proxy and clearly label confidence.

Required report sections (use these exact headings):
## Executive Summary
## Dominant Narrative Driving Price
## Sentiment Proxy by Day (Past Week)
## Narrative vs Fundamentals Divergence
## Crowding and Positioning Signals (Proxy)
## Narrative Fragility and Break Conditions
## Forward Narrative Outlook (1-3 Months)
## Actionable Implications for Traders and Investors

Rubric:
- Explain what the market is believing, not just what happened.
- Separate narrative momentum from business reality.
- Quantify tone where possible (bullish/mixed/bearish by day with evidence).
- Identify the two or three events that could rapidly flip sentiment.
- Provide an explicit confidence score for your sentiment inference.

Finish with a Markdown table named "Narrative and Sentiment Evidence Table" with columns for date/theme, sentiment direction, confidence, and implication."""
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
            "sentiment_report": report,
        }

    return social_media_analyst_node
