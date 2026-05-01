"""Human or LLM-judge rubric aligned with CFA-style pillars and the methodology-first plan.

Use with LangSmith offline evals: import ``ANALYSIS_FRAMEWORK_RUBRIC_MD`` as the judge
prompt appendix, or attach ``suggested_langsmith_dataset_metadata()`` fields to dataset rows.
"""

from __future__ import annotations

from typing import Any, Dict

# Score each item 0–2 unless noted: 0 missing, 1 partial, 2 strong.
ANALYSIS_FRAMEWORK_RUBRIC_MD = """
## Analysis framework rubric (trace → final outputs)

Score each dimension **0** (missing), **1** (partial), **2** (strong). Optionally add one-line evidence per item.

1. **Thesis clarity** — `integrated_thesis_report` has bull/base/bear one-liners and an assumption table tied to named sources/tools.
2. **Cross-report triangulation** — conflicts across market, fundamentals, forward, news, sentiment are named; integrator or debate resolves or flags them.
3. **Business & industry** — fundamentals (and forward peers where used) explain economics and competitive context with tool-cited evidence.
4. **Earnings quality** — fundamentals lane addresses cash vs accruals / recurring vs one-offs / red flags where data allows.
5. **Valuation triangulation** — at least two independent anchors (e.g. peer multiple band + forward/consensus sanity); no unsupported “cheap on P/E” alone.
6. **Risks & catalysts** — top risks and repricing catalysts explicit; linked to “what the market is missing” where applicable.
7. **Numeric discipline** — material math uses `evaluate_math_expression` or clearly cites tool numbers; no orphan figures.
8. **Verifier-lite** — `verification_notes` is OK or only minor structural warnings; scenario probabilities in forward lane roughly coherent.
9. **Tool provenance** — string tool outputs show `[tool=…] [vendor=…] [symbol=…] [as_of=…]` where applicable for triangulation.

**Regression focus:** re-run traces where items 7–9 fail; fix tool args, headers, or prompts rather than expanding prose.
""".strip()


def suggested_langsmith_dataset_metadata(ticker: str, trade_date: str) -> Dict[str, Any]:
    """Example metadata dict for a fixed (ticker, date) dataset row in LangSmith."""
    return {
        "ticker": ticker,
        "trade_date": trade_date,
        "horizon_days": 60,
        "benchmark_ticker": "SPY",
        "rubric_version": "methodology_first_v1",
        "pillars_ref": "tradingagents.agents.utils.analysis_framework",
    }


DEFAULT_RUBRIC_WEIGHTS: Dict[str, float] = {
    "thesis_clarity": 1.0,
    "triangulation": 1.2,
    "business_industry": 1.0,
    "earnings_quality": 1.2,
    "valuation_triangulation": 1.3,
    "risks_catalysts": 1.0,
    "numeric_discipline": 1.3,
    "verifier_compliance": 1.1,
    "tool_provenance": 0.9,
}
