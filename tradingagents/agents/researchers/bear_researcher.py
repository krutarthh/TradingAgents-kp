

from tradingagents.agents.utils.agent_utils import get_debate_context_reports


def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        (
            market_research_report,
            sentiment_report,
            news_report,
            fundamentals_report,
            forward_report,
        ) = get_debate_context_reports(state)

        prompt = f"""You are the Bear Researcher. Build the strongest possible downside thesis grounded in evidence.

Rules:
- Focus on fragility, downside convexity, and probability-weighted loss paths.
- Attack the strongest bull claim directly before introducing new risks.
- Debate in natural conversational language while remaining quantitative.

Required structure (use section labels in your response):
1) Core Bear Thesis
2) 1Y Downside Outlook (near-term risk pathways)
3) 3Y Structural Risk Outlook (moat decay, unit economics, macro pressure)
4) 5Y Secular Bear Case (regime shifts, disruption, policy/geopolitics)
5) Named Scenario Risk Mapping (at least two scenarios and why they hurt the stock)
6) Rebuttal to Bull's Strongest Point
7) What Would Invalidate the Bear Thesis

Output requirements:
- Include at least one quantified downside claim in each horizon section.
- Include a probability estimate for your base bear path.
- Separate temporary drawdown risks from thesis-breaking risks.
- Explicitly identify where valuation expectations are vulnerable to compression.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Forward scenarios report: {forward_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
"""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
