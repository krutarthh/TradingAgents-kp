from __future__ import annotations

from typing import Optional, Tuple

from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_sec_filing_highlights,
    get_sec_filing_sections,
    get_earnings_transcript_highlights,
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news,
    get_fear_greed_index,
)
from tradingagents.agents.utils.forward_data_tools import (
    get_analyst_estimates,
    get_peer_comparables,
    get_macro_regime,
    get_sector_etf_trends,
    get_options_implied_move,
    probability_weighted_price,
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Only applied to user-facing agents (analysts, portfolio manager).
    Internal debate agents stay in English for reasoning quality.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )


def truncate_report_for_prompt(text: str, max_chars: Optional[int]) -> str:
    """Trim long analyst reports for debate prompts. max_chars None or <=0 means no trimming."""
    raw = text or ""
    if max_chars is None or max_chars <= 0:
        return raw
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars] + f"\n… [truncated, {len(raw)} total chars]"


def get_debate_context_reports(state: dict) -> Tuple[str, str, str, str, str]:
    """Return market, sentiment, news, fundamentals, forward reports with optional per-report caps."""
    from tradingagents.dataflows.config import get_config

    cap = get_config().get("max_chars_per_report_in_debate")
    return (
        truncate_report_for_prompt(state.get("market_report") or "", cap),
        truncate_report_for_prompt(state.get("sentiment_report") or "", cap),
        truncate_report_for_prompt(state.get("news_report") or "", cap),
        truncate_report_for_prompt(state.get("fundamentals_report") or "", cap),
        truncate_report_for_prompt(state.get("forward_report") or "", cap),
    )


def build_analyst_evidence_digest(state: dict) -> str:
    """Short excerpts from each analyst report for Research Manager and Trader."""
    from tradingagents.dataflows.config import get_config

    per = int(get_config().get("analyst_evidence_digest_max_chars_per_report") or 1200)
    labels = [
        ("Market", "market_report"),
        ("Sentiment / social", "sentiment_report"),
        ("News", "news_report"),
        ("Fundamentals", "fundamentals_report"),
        ("Forward scenarios", "forward_report"),
    ]
    lines = [
        "## Analyst evidence digest",
        "Truncated excerpts from primary analyst outputs. Use with the investment plan and debate;",
        "do not treat this as the full reports.",
        "",
    ]
    for title, key in labels:
        excerpt = truncate_report_for_prompt(state.get(key) or "", per)
        if not excerpt.strip():
            lines.append(f"### {title}\n_(no report — lane skipped or no output.)_\n")
        else:
            lines.append(f"### {title}\n{excerpt}\n")
    return "\n".join(lines)


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
