# TradingAgents/graph/conditional_logic.py

from tradingagents.agents.utils.agent_states import AgentState

# Words that signal a debater is conceding / converging, which lets adaptive
# debate stop early instead of burning a fixed number of rounds.
_CONVERGENCE_MARKERS = (
    "i agree",
    "we agree",
    "concede",
    "conceding",
    "fair point",
    "consensus",
    "common ground",
    "no further disagreement",
)


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(
        self,
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        adaptive_debate=False,
        adaptive_debate_max_rounds=None,
    ):
        """Initialize with configuration parameters.

        When ``adaptive_debate`` is enabled, the bull/bear debate can run deeper
        than ``max_debate_rounds`` (up to ``adaptive_debate_max_rounds``) as long
        as the two sides still disagree, and stops early once a side concedes.
        """
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
        self.adaptive_debate = adaptive_debate
        self.adaptive_debate_max_rounds = adaptive_debate_max_rounds or max(
            max_debate_rounds, 3
        )

    @staticmethod
    def _shows_convergence(text: str) -> bool:
        low = (text or "").lower()
        return any(marker in low for marker in _CONVERGENCE_MARKERS)

    def _debate_round_cap(self, state: AgentState) -> int:
        """Effective turn cap for the bull/bear debate (adapts to disagreement)."""
        base_cap = 2 * self.max_debate_rounds
        if not self.adaptive_debate:
            return base_cap
        # Stop early if the latest turn signals agreement/convergence.
        latest = state["investment_debate_state"].get("current_response", "")
        if self._shows_convergence(latest):
            return base_cap
        return max(base_cap, 2 * self.adaptive_debate_max_rounds)

    def should_continue_market(self, state: AgentState):
        """Determine if market analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_market"
        return "Msg Clear Market"

    def should_continue_social(self, state: AgentState):
        """Determine if social media analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_social"
        return "Msg Clear Social"

    def should_continue_news(self, state: AgentState):
        """Determine if news analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_news"
        return "Msg Clear News"

    def should_continue_fundamentals(self, state: AgentState):
        """Determine if fundamentals analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_fundamentals"
        return "Msg Clear Fundamentals"

    def should_continue_forward(self, state: AgentState):
        """Determine if forward analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_forward"
        return "Msg Clear Forward"

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""

        if state["investment_debate_state"]["count"] >= self._debate_round_cap(state):
            return "Verification Gate"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        if (
            state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
        ):  # 3 rounds of back-and-forth between 3 agents
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"

    # Map a blamed lane to its analyst node name for targeted re-runs.
    _LANE_NODES = {
        "fundamentals": "Fundamentals Analyst",
        "forward": "Forward Analyst",
    }

    def should_continue_after_verification(self, state: AgentState) -> str:
        """Route after the verification gate.

        On a hard fail, optionally re-run just the analyst lane that caused the
        failure (when ``verification_rerun_lane`` is enabled and that lane node
        is part of the graph); otherwise re-run the Thesis Integrator. On
        pass/warn, continue to the Research Manager.
        """
        status = (state.get("verification_status") or "pass").lower()
        if status != "fail":
            return "Research Manager"

        from tradingagents.dataflows.config import get_config

        if get_config().get("verification_rerun_lane", False):
            lane = (state.get("verification_failed_lane") or "").strip().lower()
            node = self._LANE_NODES.get(lane)
            if node and node in getattr(self, "_available_lane_nodes", set()):
                return node
        return "Thesis Integrator"
