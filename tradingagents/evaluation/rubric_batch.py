"""Offline rubric artifacts for pipeline eval (LangSmith-style scoring without requiring traces)."""

from __future__ import annotations

from pathlib import Path

from tradingagents.evaluation.langsmith_rubric import ANALYSIS_FRAMEWORK_RUBRIC_MD


def write_offline_rubric_pack(out_dir: Path) -> Path:
    """Write rubric text and pointers for human or LLM-as-judge scoring per saved run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rubric_path = out_dir / "RUBRIC_OFFLINE_SCORING.md"
    body = f"""# Offline analysis-framework rubric

Use this appendix when scoring traces or saved reports outside LangSmith.

Attach dataset metadata per row via `suggested_langsmith_dataset_metadata` from
`tradingagents.evaluation.langsmith_rubric`.

---

{ANALYSIS_FRAMEWORK_RUBRIC_MD}

---

## How to use with this eval batch

1. Open each run's `full_states_log_<trade_date>.json` under `results_dir` / ticker / TradingAgentsStrategy_logs.
2. Score dimensions 0–2 per `ANALYSIS_FRAMEWORK_RUBRIC_MD`.
3. Compare outcome columns in `eval_results.csv` only after process-quality review.

Outcome metrics (forward alpha) do not validate reasoning quality alone.
"""
    rubric_path.write_text(body, encoding="utf-8")
    return rubric_path
