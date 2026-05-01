from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_analyst_estimates(
    ticker: Annotated[str, "Ticker symbol"],
) -> str:
    """Retrieve analyst targets, recommendation trends, and earnings/revenue estimates."""
    return route_to_vendor("get_analyst_estimates", ticker)


@tool
def get_peer_comparables(
    ticker: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """Retrieve peer and sector-relative performance context."""
    return route_to_vendor("get_peer_comparables", ticker, curr_date)


@tool
def get_macro_regime(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """Retrieve macro regime proxies (volatility, rates, dollar, commodities, credit)."""
    return route_to_vendor("get_macro_regime", curr_date)


@tool
def get_sector_etf_trends(
    sector_or_etf: Annotated[str, "Sector name or ETF ticker"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """Retrieve sector ETF trend and relative-strength metrics."""
    return route_to_vendor("get_sector_etf_trends", sector_or_etf, curr_date)


@tool
def get_options_implied_move(
    ticker: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """Estimate implied move using nearest-expiry ATM straddle."""
    return route_to_vendor("get_options_implied_move", ticker, curr_date)


@tool
def probability_weighted_price(
    bull_price: Annotated[float, "Bull-case target price"],
    bull_prob: Annotated[float, "Bull probability (0..1)"],
    base_price: Annotated[float, "Base-case target price"],
    base_prob: Annotated[float, "Base probability (0..1)"],
    bear_price: Annotated[float, "Bear-case target price"],
    bear_prob: Annotated[float, "Bear probability (0..1)"],
) -> str:
    """Deterministic expected-price helper from bull/base/bear targets and probabilities."""
    probs = [bull_prob, base_prob, bear_prob]
    if any(p < 0 or p > 1 for p in probs):
        return "Error: probabilities must each be between 0 and 1"
    total = sum(probs)
    if total <= 0:
        return "Error: probability sum must be > 0"
    norm = [p / total for p in probs]
    expected = bull_price * norm[0] + base_price * norm[1] + bear_price * norm[2]
    return (
        f"expected_price={expected:.4f}; "
        f"normalized_probs=(bull={norm[0]:.4f}, base={norm[1]:.4f}, bear={norm[2]:.4f})"
    )
