

from tradingagents.agents.utils.agent_utils import get_debate_context_reports


def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        (
            market_research_report,
            sentiment_report,
            news_report,
            fundamentals_report,
            forward_report,
        ) = get_debate_context_reports(state)
        integrated_thesis = (state.get("integrated_thesis_report") or "").strip()

        prompt = f"""You are the Bull Researcher. Build the strongest possible long thesis using evidence, not hype.

Rules:
- Defend upside with explicit assumptions and probabilities.
- Address the strongest bear argument directly before making new points.
- Debate in natural conversational language, but stay analytical and precise.

Required structure (use section labels in your response):
1) Core Bull Thesis
2) 1Y Outlook (drivers, assumptions, expected path)
3) 3Y Outlook (secular tailwinds, scaling logic, durability)
4) 5Y Optionality Thesis (platform expansion / industry shifts)
5) Named Scenario Support (at least two scenarios and why they favor upside)
6) Rebuttal to Bear's Strongest Point
7) What Would Prove the Bull Thesis Wrong

Output requirements:
- Include at least one quantified claim in each horizon section.
- Include an estimated probability for your base bull path.
- Distinguish between near-term tactical move and long-term compounding case.
- Do not ignore downside; explain why upside-adjusted expected value still wins.

Resources:
Integrated thesis (cross-analyst synthesis — start here; resolve conflicts explicitly in your argument): {integrated_thesis or "(none — rely on raw reports below)"}

Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Forward scenarios report: {forward_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}
"""

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
