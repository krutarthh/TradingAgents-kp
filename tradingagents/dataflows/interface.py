from typing import Annotated

# Import from vendor-specific modules
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_forward import (
    get_analyst_estimates_yfinance,
    get_macro_regime_yfinance,
    get_macro_regime_yfinance_complement,
    get_options_implied_move_yfinance,
    get_peer_comparables_yfinance,
    get_sector_etf_trends_yfinance,
)
from .fred_macro import get_macro_regime_fred
from .config import DataVendorSkipped, get_config
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .cnn_sentiment import get_fear_greed_index_cnn
from .api_ninjas_sec import (
    get_earnings_transcript_highlights_stub,
    get_sec_filing_highlights_ninjas,
    get_sec_filing_sections_ninjas,
)
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .alpha_vantage_common import AlphaVantageRateLimitError
from .tool_response_metadata import prefix_string_body

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement",
            "get_sec_filing_highlights",
            "get_sec_filing_sections",
            "get_earnings_transcript_highlights",
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
            "get_fear_greed_index",
        ]
    },
    "forward_data": {
        "description": "Forward-looking estimates, macro regime, and peer comparables",
        "tools": [
            "get_analyst_estimates",
            "get_peer_comparables",
            "get_macro_regime",
            "get_sector_etf_trends",
            "get_options_implied_move",
        ],
    },
}

VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
]


def get_macro_regime_routed(curr_date: str) -> str:
    """Official FRED macro plus yfinance oil/gold/credit/DXY proxies."""
    fred_block = get_macro_regime_fred(curr_date)
    complement = get_macro_regime_yfinance_complement(curr_date)
    return f"{fred_block}\n\n{complement}"


# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    # technical_indicators
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    # fundamental_data
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    "get_sec_filing_highlights": {
        "api_ninjas": get_sec_filing_highlights_ninjas,
    },
    "get_sec_filing_sections": {
        "api_ninjas": get_sec_filing_sections_ninjas,
    },
    "get_earnings_transcript_highlights": {
        "api_ninjas": get_earnings_transcript_highlights_stub,
    },
    # news_data
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
    "get_fear_greed_index": {
        "yfinance": get_fear_greed_index_cnn,
    },
    # forward_data
    "get_analyst_estimates": {
        "yfinance": get_analyst_estimates_yfinance,
    },
    "get_peer_comparables": {
        "yfinance": get_peer_comparables_yfinance,
    },
    "get_macro_regime": {
        "yfinance": get_macro_regime_routed,
    },
    "get_sector_etf_trends": {
        "yfinance": get_sector_etf_trends_yfinance,
    },
    "get_options_implied_move": {
        "yfinance": get_options_implied_move_yfinance,
    },
}


def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")

def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to a single configured vendor (strict mode)."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    configured_vendors = [v.strip() for v in str(vendor_config).split(",") if v.strip()]
    if not configured_vendors:
        raise RuntimeError(f"No configured vendor for '{method}'")
    vendor = configured_vendors[0]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")
    if vendor not in VENDOR_METHODS[method]:
        raise RuntimeError(f"Configured vendor '{vendor}' not available for '{method}'")

    vendor_impl = VENDOR_METHODS[method][vendor]
    impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl
    try:
        result = impl_func(*args, **kwargs)
    except (AlphaVantageRateLimitError, DataVendorSkipped) as exc:
        raise RuntimeError(
            f"Configured vendor '{vendor}' failed for '{method}': {exc}"
        ) from exc
    if isinstance(result, str):
        return prefix_string_body(method, vendor, result, args, kwargs)
    return result