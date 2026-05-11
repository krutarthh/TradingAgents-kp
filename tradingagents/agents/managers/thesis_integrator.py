"""Synthesizes analyst reports into a single thesis brief before bull/bear debate."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from tradingagents.agents.utils.agent_utils import (
    build_analyst_evidence_digest,
    build_instrument_context,
)
from tradingagents.dataflows.config import get_config


def create_thesis_integrator(llm):
    """LLM node: unified thesis, assumption table, conflicts, valuation non-negotiables."""

    def thesis_integrator_node(state) -> dict:
        instrument = build_instrument_context(state["company_of_interest"])
        trade_date = state["trade_date"]

        if not get_config().get("enable_thesis_integrator", True):
            digest = build_analyst_evidence_digest(state)
            return {
                "integrated_thesis_report": (
                    "## Unified thesis\n"
                    "_Thesis integrator LLM disabled; analyst digest follows._\n\n"
                    f"{digest}\n\n"
                    "## Assumptions table\n"
                    "| Assumption | Source | If wrong, what breaks |\n"
                    "|------------|--------|----------------------|\n"
                    "| (populate from full reports when re-enabling integrator) | digest | — |\n\n"
                    "## Cross-sectional facts (market vs sector vs benchmark)\n"
                    "- Pull RS vs SPY / sector ETF lines **only** from digest excerpts (Market / Forward).\n\n"
                    "## Cross-report conflicts\n"
                    "- Compare digest sections above for disagreements.\n\n"
                    "## Valuation non-negotiables\n"
                    "- Use fundamentals + forward full reports for dual-anchor valuation.\n\n"
                    "## Catalysts and repricing\n"
                    "- See forward and news excerpts in digest.\n"
                )
            }

        prompt = f"""You are the Thesis Integrator. You do not use external tools. Public / tool-derived analyst outputs are the only evidence.

{instrument}
As-of trade date: {trade_date}

--- MARKET REPORT ---
{state.get("market_report") or "(empty)"}

--- SENTIMENT REPORT ---
{state.get("sentiment_report") or "(empty)"}

--- NEWS REPORT ---
{state.get("news_report") or "(empty)"}

--- FUNDAMENTALS REPORT ---
{state.get("fundamentals_report") or "(empty)"}

--- FORWARD REPORT ---
{state.get("forward_report") or "(empty)"}

---

Produce the following sections with these EXACT markdown headings:

## Unified thesis
- One line each for bull, base, and bear (outcome-focused, not slogans).

## Cross-sectional facts (market vs sector vs benchmark)
- Short bullet list **only** recombined from numbers already present in Market or Forward reports (e.g. relative strength vs SPY, sector ETF momentum class, peer return rankings).
- After each bullet, note parenthetically which report the figures came from (Market vs Forward). Do not invent new statistics.

## Assumptions table
| Assumption | Source report / tool named in text | If wrong, what breaks |

## Cross-report conflicts
- Bullet list where market, fundamentals, forward, news, or sentiment disagree; state which you trust more and why.

## Valuation non-negotiables
- Bullet list: what must be true for relative valuation (peers/multiples) and what check from forward/fundamentals anchors an absolute or reverse-DCF style sanity check.

## Catalysts and repricing
- What would force the market to re-price the name (2–4 bullets).

Be concise; no new numbers unless they are recombinations of numbers already in the reports."""

        response = llm.invoke([HumanMessage(content=prompt)])
        return {"integrated_thesis_report": response.content}

    return thesis_integrator_node
