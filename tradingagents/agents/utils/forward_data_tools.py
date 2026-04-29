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
