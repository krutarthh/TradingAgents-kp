from cli.models import AnalystType

CLI_CONFIG = {
    # Announcements
    "announcements_url": "https://api.tauric.ai/v1/announcements",
    "announcements_timeout": 1.0,
    "announcements_fallback": "[cyan]For more information, please visit[/cyan] [link=https://github.com/TauricResearch]https://github.com/TauricResearch[/link]",
}

# Fixed TUI defaults — only the ticker is prompted interactively.
CLI_DEFAULTS = {
    "output_language": "English",
    "llm_provider": "ollama",
    "backend_url": "https://ollama.com/v1",
    "quick_think_llm": "gemma4:31b-cloud",
    "deep_think_llm": "gemma4:31b-cloud",
    "research_depth": 3,
    "analysts": list(AnalystType),
}
