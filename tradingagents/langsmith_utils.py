"""Optional LangSmith tracing (LangChain env convention).

Tracing captures LLM generations, tool calls, and LangGraph steps in the LangSmith UI
when ``LANGCHAIN_TRACING_V2=true`` and ``LANGCHAIN_API_KEY`` are set.

Offline evaluation: see ``tradingagents.evaluation.langsmith_rubric`` for a trace-scoring
rubric aligned with the analysis framework.

See https://docs.smith.langchain.com/
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


def configure_langsmith_from_config(config: Dict[str, Any]) -> None:
    """Apply ``langsmith_*`` entries from app config to process environment.

    - ``langsmith_tracing`` ``True`` / ``False`` forces tracing on or off.
    - ``None`` leaves ``LANGCHAIN_TRACING_V2`` unchanged (use ``.env`` only).
    - ``langsmith_project`` sets ``LANGCHAIN_PROJECT`` when non-empty.
    """
    tracing: Optional[bool] = config.get("langsmith_tracing")
    if tracing is True:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
    elif tracing is False:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"

    project = config.get("langsmith_project")
    if project is not None and str(project).strip():
        os.environ["LANGCHAIN_PROJECT"] = str(project).strip()
