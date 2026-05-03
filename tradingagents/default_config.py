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
    # LangGraph recursion_limit (one increment per node execution). Tool-heavy
    # analysts (SEC sections, fundamentals + calculators) can exceed 100 quickly.
    "max_recur_limit": 300,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
        "forward_data": "yfinance",          # Options: yfinance
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
        "get_sec_filing_highlights": "api_ninjas",
        "get_sec_filing_sections": "api_ninjas",
        "get_earnings_transcript_highlights": "api_ninjas",
        "get_fear_greed_index": "yfinance",
    },
    # LLM context: cap each analyst report inlined in bull/bear/risk prompts (None = no cap)
    "max_chars_per_report_in_debate": None,
    # Excerpt length per report in Research Manager / Trader evidence digest
    "analyst_evidence_digest_max_chars_per_report": 1200,
    # Methodology extras (thesis integrator + verifier-lite before Research Manager)
    "enable_thesis_integrator": True,
    "enable_verification_gate": True,
    "verification_max_retries": 1,
    "enable_verifier_plus_fail_block": True,
    "enable_valuation_sensitivity_tables": True,
    "enable_filing_transcript_tools": True,
    "eval_holding_days": 60,
    "eval_benchmark_ticker": "SPY",
    # Preferred analyst order: list "forward" last so consensus/macro are freshest before integration
    "recommended_analyst_order": ["market", "social", "news", "fundamentals", "forward"],
    # LangSmith: None = only env vars (LANGCHAIN_TRACING_V2); True/False forces on/off
    "langsmith_tracing": None,
    "langsmith_project": "TradingAgents",
}
