"""Extract the 5-tier portfolio rating from the Portfolio Manager's decision.

The Portfolio Manager produces a typed ``PortfolioDecision`` via structured
output and renders it to markdown that always carries a ``**Rating**: X``
header (see :func:`tradingagents.agents.schemas.render_pm_decision`).  The
deterministic heuristic in :mod:`tradingagents.agents.utils.rating` is more
than sufficient to extract that rating; no extra LLM call is needed.

This module exists for backwards compatibility with callers that expect a
``SignalProcessor.process_signal(text)`` interface.
"""

from __future__ import annotations

from typing import Any, Dict

from tradingagents.agents.utils.decision_signal import signal_from_markdown
from tradingagents.agents.utils.rating import parse_rating


class SignalProcessor:
    """Read the rating (and full signal) out of a Portfolio Manager decision."""

    def __init__(self, quick_thinking_llm: Any = None):
        # The LLM argument is accepted for backwards compatibility but no
        # longer used: the PM's structured output guarantees the rating is
        # parseable from the rendered markdown without a second LLM call.
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> str:
        """Return one of Buy / Overweight / Hold / Underweight / Sell."""
        return parse_rating(full_signal)

    def process_signal_rich(self, full_signal: str) -> Dict[str, Any]:
        """Return the full signal (rating, score, confidence, targets, probs).

        Best-effort parse from the rendered PM markdown for callers that only
        have the decision string. When the graph has the structured PM object,
        ``final_state['final_decision_signal']`` is the authoritative source.
        """
        return signal_from_markdown(full_signal)
