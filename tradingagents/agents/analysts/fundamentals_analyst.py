from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
    get_language_instruction,
)
from tradingagents.agents.utils.analysis_framework import get_analysis_contract_suffix
from tradingagents.agents.utils.calculator_tool import evaluate_math_expression
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_insider_transactions,
            evaluate_math_expression,
        ]

        system_message = (
            """You are the Fundamentals Analyst. Produce an institutional-grade report that is forward-looking, not just descriptive.

Required process:
1) Call `get_fundamentals` first for company profile and valuation baselines.
2) Call `get_income_statement`, `get_balance_sheet`, and `get_cashflow` to verify trend direction.
3) Call `get_insider_transactions` to assess management conviction and governance signals.
4) Use `evaluate_math_expression` whenever you combine ratios, margins, or growth rates—do not chain arithmetic only in prose.
5) Use evidence from all tools before writing your final report.

Required report sections (use these exact headings):
## Executive Summary
## Business Model and Competitive Moat
## Unit Economics and Margin Trajectory
## Growth Durability and Capital Allocation
## Balance Sheet Strength and Funding Risk
## Earnings Quality and Cash Conversion
## Valuation Triangulation (two anchors minimum)
## Management/Insider Signal Check
## Forward 12-36 Month Fundamental Outlook
## Bull, Base, and Bear Fundamental Scenarios
## Thesis Invalidation Triggers
## Catalyst Calendar
## Actionable Implications for Traders and Investors

Rubric:
- **Valuation triangulation**: you MUST use at least two independent anchors (e.g. relative multiple vs a peer or sector reference from tool data, plus a narrative implied-growth or margin sanity check). A single headline P/E or EV/EBITDA claim without peer/context is insufficient.
- **Earnings quality**: compare profit vs cash generation using statements (e.g., net income path vs operating cash flow). Flag large or persistent gaps, unusual one-offs in revenue or expenses, and any concentration risks visible in the tool outputs. If footnotes are not in the data, say what you cannot see.
- Anchor claims in specific figures (growth rates, margins, cash flow, leverage, dilution, returns).
- Explicitly separate operating performance from non-recurring accounting noise where visible.
- Include a 1-year and 3-year outlook with assumptions.
- In scenarios, provide probabilities that sum to roughly 1.0 and what has to happen for each scenario to play out.
- Explain what would make today's thesis wrong.
- Be nuanced: discuss both upside and downside, then conclude with the highest-conviction interpretation.

Finish with a Markdown table named "Key Fundamental Evidence Table" that summarizes the most decision-relevant metrics, trend direction, and implication."""
            + " Use tools: `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_insider_transactions`, and `evaluate_math_expression`."
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
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
