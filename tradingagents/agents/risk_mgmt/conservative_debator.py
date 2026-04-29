

from tradingagents.agents.utils.agent_utils import get_debate_context_reports


def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        (
            market_research_report,
            sentiment_report,
            news_report,
            fundamentals_report,
            forward_report,
        ) = get_debate_context_reports(state)

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Conservative Risk Analyst, your objective is capital preservation, drawdown control, and survivability across regimes.

You must:
- Identify hidden downside convexity and fragile assumptions in the trader's plan.
- Reference at least two named future scenarios (e.g., war escalation, AI capex pullback, recession/hard landing, regulatory shock) and explain why they argue for a defensive stance.
- Directly challenge aggressive and neutral arguments where they underprice risk.

Here is the trader's decision:

{trader_decision}

Your task is to counter Aggressive and Neutral analysts, highlighting where they overlook downside and fail to prioritize sustainability. Use:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Forward Scenarios Report: {forward_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Output requirements:
- Include tactical (0-6 week) defense and strategic (12-36 month) capital-protection framing.
- Specify concrete downgrade/de-risk triggers.
- Keep the response conversational with no special formatting."""

        response = llm.invoke(prompt)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
