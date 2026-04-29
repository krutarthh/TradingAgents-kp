

from tradingagents.agents.utils.agent_utils import get_debate_context_reports


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        (
            market_research_report,
            sentiment_report,
            news_report,
            fundamentals_report,
            forward_report,
        ) = get_debate_context_reports(state)

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Neutral Risk Analyst, provide a balanced risk-adjusted recommendation that integrates upside optionality and downside control.

You must:
- Reconcile the strongest aggressive and conservative claims.
- Reference at least two named future scenarios and show how portfolio risk changes under each.
- Recommend a moderate, robust strategy that can survive uncertainty.

Here is the trader's decision:

{trader_decision}

Your task is to challenge both Aggressive and Conservative analysts where they overreach. Use:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Forward Scenarios Report: {forward_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the conservative analyst: {current_conservative_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Output requirements:
- Include tactical (0-6 week) and strategic (12-36 month) risk framing.
- Present a base-case allocation/risk stance and clear adjustment triggers.
- Keep the response conversational with no special formatting."""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
