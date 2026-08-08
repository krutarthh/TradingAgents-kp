"""Post-analysis chat: ask the model why it reached the final decision."""

from __future__ import annotations

from typing import Any, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()

_EXIT_WORDS = {"exit", "quit", "q", "done", "bye"}
_SECTION_CAP = 3500


def _clip(text: Optional[str], max_chars: int = _SECTION_CAP) -> str:
    raw = (text or "").strip()
    if not raw:
        return "(empty)"
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars] + f"\n\n… [truncated, {len(raw)} total chars]"


def build_decision_briefing(
    final_state: dict,
    ticker: str,
    analysis_date: str,
    decision_label: Optional[str] = None,
) -> str:
    """Compact briefing the chat model uses as ground truth."""
    debate = final_state.get("investment_debate_state") or {}
    risk = final_state.get("risk_debate_state") or {}

    parts = [
        f"# Analysis briefing for {ticker} as of {analysis_date}",
        "",
        f"**Final decision signal:** {decision_label or '(see Portfolio Manager section below)'}",
        "",
        "## Portfolio Manager final decision",
        _clip(final_state.get("final_trade_decision") or risk.get("judge_decision"), 6000),
        "",
        "## Research Manager plan",
        _clip(final_state.get("investment_plan") or debate.get("judge_decision")),
        "",
        "## Trader proposal",
        _clip(final_state.get("trader_investment_plan")),
        "",
        "## Integrated thesis",
        _clip(final_state.get("integrated_thesis_report"), 2500),
        "",
        "## Market Analyst",
        _clip(final_state.get("market_report")),
        "",
        "## News / Macro Analyst",
        _clip(final_state.get("news_report")),
        "",
        "## Fundamentals Analyst",
        _clip(final_state.get("fundamentals_report")),
        "",
        "## Forward Analyst",
        _clip(final_state.get("forward_report")),
        "",
        "## Social / Sentiment Analyst",
        _clip(final_state.get("sentiment_report"), 2000),
        "",
        "## Bull vs Bear (excerpts)",
        "### Bull",
        _clip(debate.get("bull_history"), 2000),
        "### Bear",
        _clip(debate.get("bear_history"), 2000),
        "",
        "## Risk debate (excerpts)",
        "### Aggressive",
        _clip(risk.get("aggressive_history"), 1500),
        "### Conservative",
        _clip(risk.get("conservative_history"), 1500),
        "### Neutral",
        _clip(risk.get("neutral_history"), 1500),
    ]
    return "\n".join(parts)


def _system_prompt(briefing: str) -> str:
    return (
        "You are the post-analysis explainer for a multi-agent trading research run.\n"
        "Your job is to help the user understand WHY the team reached its decision.\n\n"
        "Rules:\n"
        "- Answer only from the briefing below. Do not invent prices, metrics, or tool outputs.\n"
        "- If something is missing from the briefing, say so clearly.\n"
        "- Prefer concrete citations (which agent/section, key numbers, risks, invalidation).\n"
        "- Explain disagreements between bull/bear/risk analysts when relevant.\n"
        "- Keep answers concise unless the user asks for depth.\n"
        "- Do not give new buy/sell advice that contradicts the recorded decision unless the "
        "user explicitly asks you to critique it; then label critique as opinion on the briefing.\n\n"
        "=== BRIEFING START ===\n"
        f"{briefing}\n"
        "=== BRIEFING END ==="
    )


def run_decision_chat(
    llm: Any,
    final_state: dict,
    ticker: str,
    analysis_date: str,
    decision_label: Optional[str] = None,
) -> None:
    """Interactive Q&A loop about the completed analysis decision."""
    briefing = build_decision_briefing(
        final_state, ticker, analysis_date, decision_label=decision_label
    )
    messages: List[Any] = [SystemMessage(content=_system_prompt(briefing))]

    console.print()
    console.print(
        Panel(
            "[bold]Decision Chat[/bold]\n"
            f"Ask why the team rated [cyan]{ticker}[/cyan] the way it did.\n"
            "[dim]Type exit / quit / q when done.[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print(
        "[dim]Try: Why this rating? What were the top risks? "
        "How did Fear & Greed / macro factor in? Where did bull and bear disagree?[/dim]\n"
    )

    while True:
        try:
            question = console.input("[bold green]You>[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Leaving decision chat.[/dim]")
            break

        if not question:
            continue
        if question.lower() in _EXIT_WORDS:
            console.print("[dim]Leaving decision chat.[/dim]")
            break

        messages.append(HumanMessage(content=question))
        try:
            with console.status("[cyan]Thinking…[/cyan]", spinner="dots"):
                response = llm.invoke(messages)
            answer = getattr(response, "content", None) or str(response)
            if isinstance(answer, list):
                # Some providers return content blocks
                answer = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in answer
                )
        except Exception as exc:
            console.print(f"[red]Chat error:[/red] {exc}")
            messages.pop()
            continue

        messages.append(AIMessage(content=answer))
        console.print()
        console.print(Panel(Markdown(answer), title="Assistant", border_style="blue"))
        console.print()
