"""CFA-style equity analysis mapping: pillars, owners, shared prompt contract.

Used by analyst prompts and the thesis integrator. See CFA Institute
equity research guidelines for report structure inspiration.
"""

from __future__ import annotations

from typing import Dict, List

# Each pillar maps to the primary state/report field that should cover it.
# Cross-lane synthesis is explicit merge (not owned by a single analyst).
PILLAR_TO_REPORT: Dict[str, str] = {
    "Cross_report_synthesis_and_conflicts": "integrated_thesis_report (thesis integrator node)",
    "Company_economics_and_drivers": "fundamentals_report",
    "Industry_and_competitive_position": "fundamentals_report, forward_report (peers/sector), news_report",
    "Financial_history_and_earnings_quality": "fundamentals_report",
    "Valuation_triangulation": "fundamentals_report, forward_report",
    "Catalysts_mispricing_repricing": "forward_report, news_report, market_report",
    "Technical_execution_and_timing": "market_report",
    "Narrative_sentiment_proxy": "sentiment_report",
    "Macro_liquidity_context": "news_report, forward_report",
}

# Reverse lookup: which pillars a report should explicitly address
REPORT_PILLARS_COVERAGE: Dict[str, List[str]] = {
    "integrated_thesis_report": ["Cross_report_synthesis_and_conflicts"],
    "market_report": ["Technical_execution_and_timing", "Catalysts_mispricing_repricing"],
    "sentiment_report": ["Narrative_sentiment_proxy"],
    "news_report": ["Macro_liquidity_context", "Industry_and_competitive_position", "Catalysts_mispricing_repricing"],
    "fundamentals_report": [
        "Company_economics_and_drivers",
        "Financial_history_and_earnings_quality",
        "Industry_and_competitive_position",
        "Valuation_triangulation",
    ],
    "forward_report": [
        "Valuation_triangulation",
        "Catalysts_mispricing_repricing",
        "Industry_and_competitive_position",
    ],
}


ANALYSIS_CONTRACT_SUFFIX = """

---

Analysis contract (mandatory for this report):
- For each material claim, use: **Fact** → **Evidence (name the tool, e.g. get_stock_data / get_fundamentals)** → **Implication** → **Confidence (High/Medium/Low)**.
- Every numeric value must cite which tool output it came from; if unavailable, write "Unknown from tools" and do not guess.
- You are responsible for these pillars: see REPORT_PILLARS_COVERAGE for your lane in the codebase (`tradingagents/agents/utils/analysis_framework.py`).
"""


def get_analysis_contract_suffix() -> str:
    """Short block appended to analyst system prompts."""
    return ANALYSIS_CONTRACT_SUFFIX
