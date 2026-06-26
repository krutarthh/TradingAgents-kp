import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings
    "llm_provider": "nvidia",
    "quick_think_llm": "glm-4.7",
    "deep_think_llm": "glm-4.7",
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    # Adaptive debate: when True, the bull/bear debate runs deeper while the two
    # sides still disagree (up to adaptive_debate_max_rounds) and stops early on
    # convergence. Default False preserves the fixed-depth behavior.
    "adaptive_debate": True,
    "adaptive_debate_max_rounds": 3,
    # LangGraph recursion_limit (one increment per node execution). Tool-heavy
    # analysts (SEC sections, fundamentals + calculators) can exceed 100 quickly.
    "max_recur_limit": 300,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        # Comma-separated = try in order (rate limits / skipped vendors fall through).
        "core_stock_apis": "yfinance,alpha_vantage",
        "technical_indicators": "yfinance,alpha_vantage",
        "fundamental_data": "yfinance,alpha_vantage",
        "news_data": "yfinance,alpha_vantage",
        "social_data": "stocktwits",
        "ownership_data": "yfinance",
        "forward_data": "yfinance",
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
        "get_sec_filing_highlights": "api_ninjas",
        "get_sec_filing_sections": "api_ninjas",
        # Try FMP first (point-in-time dated rows), then Alpha Vantage, then stub.
        "get_earnings_transcript_highlights": "financial_modeling_prep,alpha_vantage,stub",
        # Point-in-time consensus via FMP when keyed, else live Yahoo snapshot.
        "get_analyst_estimates": "financial_modeling_prep,yfinance",
        "get_fear_greed_index": "yfinance",
        "get_news": "yfinance,finnhub,alpha_vantage",
        "get_earnings_calendar": "yfinance,finnhub",
    },
    # LLM context: cap each analyst report inlined in bull/bear/risk prompts (None = no cap)
    "max_chars_per_report_in_debate": 12000,
    # Excerpt length per report in Research Manager / Trader evidence digest
    "analyst_evidence_digest_max_chars_per_report": 1800,
    # Methodology extras (thesis integrator + verifier-lite before Research Manager)
    "enable_thesis_integrator": True,
    "enable_verification_gate": True,
    "verification_max_retries": 1,
    "enable_verifier_plus_fail_block": True,
    # Promote a badly-off scenario-probability sum from a warning to a hard fail.
    "enable_verifier_numeric_reconciliation": True,
    # On a hard verification fail, re-run just the blamed analyst lane
    # (fundamentals/forward) instead of only the Thesis Integrator.
    "verification_rerun_lane": True,
    "enable_valuation_sensitivity_tables": True,
    "enable_filing_transcript_tools": True,
    "eval_holding_days": 60,
    "eval_benchmark_ticker": "SPY",
    # Historical eval: enforce point-in-time data (no live yfinance .info, FRED end dates, etc.)
    "eval_strict_temporal": False,
    "eval_cutoff_date": None,
    # Live shadow book: append PM final_decision_signal rows to this CSV path (None = off).
    "live_shadow_book_path": os.getenv(
        "TRADINGAGENTS_LIVE_SHADOW_BOOK",
        os.path.join(_TRADINGAGENTS_HOME, "live_shadow_book.csv"),
    ),
    # Preferred analyst order: list "forward" last so consensus/macro are freshest before integration
    "recommended_analyst_order": ["market", "social", "news", "fundamentals", "forward"],
    # LangSmith: None = only env vars (LANGCHAIN_TRACING_V2); True/False forces on/off
    "langsmith_tracing": None,
    "langsmith_project": "TradingAgents",
}
