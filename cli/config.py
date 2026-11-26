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
    "llm_provider": "openai",
    "backend_url": "https://api.servicesessentials.ibm.com/v1/chat-models",
    "quick_think_llm": "gpt-6-luna",
    "deep_think_llm": "gpt-6-luna",
    "research_depth": 3,
    "analysts": list(AnalystType),
}
