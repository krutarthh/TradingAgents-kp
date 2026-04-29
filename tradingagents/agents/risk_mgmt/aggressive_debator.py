

from tradingagents.agents.utils.agent_utils import get_debate_context_reports


def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        (
            market_research_report,
            sentiment_report,
            news_report,
            fundamentals_report,
            forward_report,
        ) = get_debate_context_reports(state)

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Aggressive Risk Analyst, champion high-reward opportunities and challenge excessive caution.

You must:
- Make a high-conviction upside case with clear risk-reward asymmetry.
- Reference at least two named future scenarios (e.g., AI capex acceleration, rate-cut cycle, geopolitics de-escalation) and explain why they favor an aggressive stance.
- Directly rebut conservative and neutral points with evidence.

Here is the trader's decision:

{trader_decision}

Your task is to create a compelling case for the trader's decision by critiquing conservative and neutral stances and showing where caution can miss asymmetric upside. Incorporate:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Forward Scenarios Report: {forward_report}
Here is the current conversation history: {history} Here are the last arguments from the conservative analyst: {current_conservative_response} Here are the last arguments from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Output requirements:
- Include tactical (0-6 week) and strategic (12-36 month) upside path.
- State what would invalidate your aggressive stance.
- Keep the response conversational with no special formatting."""

        response = llm.invoke(prompt)

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
