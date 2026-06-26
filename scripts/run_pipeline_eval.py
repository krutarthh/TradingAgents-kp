#!/usr/bin/env python3
"""Historical pipeline evaluation: run TradingAgents per (ticker, anchor date), join forward returns.

Defaults match long-term eval plan: Ollama Cloud ``gemma4:31b-cloud``, multi-horizon labels.

Examples::

    python scripts/run_pipeline_eval.py --preflight-only --universe tradingagents/evaluation/universe_lt_eval.json

    python scripts/run_pipeline_eval.py --universe ... --out ./eval_out --workers 1

Environment: ``OLLAMA_API_KEY`` for Ollama Cloud — loaded from the repo ``.env`` (project root) automatically; shell export optional.
Parallel runs use separate processes (default ``--workers`` ≈ min(4, CPU count)); use ``--workers 1`` for sequential. Heavy parallelism may hit provider rate limits.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

# Project root on sys.path when run as script
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.evaluation.preflight import preflight_pairs, preflight_report
from tradingagents.evaluation.rubric_batch import write_offline_rubric_pack
from tradingagents.evaluation.parallel_worker import run_single_pipeline_eval


def _load_universe(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_existing_csv(path: Path) -> List[Dict[str, Any]]:
    """Read prior eval_results.csv into a list of dict rows (string-typed)."""
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _row_needs_rerun(row: Dict[str, Any]) -> bool:
    """A row needs rerun if it has an error or no rating string."""
    err = (row.get("error") or "").strip()
    rating = (row.get("rating") or "").strip()
    return bool(err) or not rating


def _coerce_csv_floats(row: Dict[str, Any], horizons: List[int]) -> Dict[str, Any]:
    """Convert string return columns from CSV back to floats (or None)."""
    out = dict(row)
    for h in horizons:
        for col in (f"raw_return_{h}d", f"alpha_return_{h}d"):
            val = out.get(col)
            if val is None or val == "":
                out[col] = None
            else:
                try:
                    out[col] = float(val)
                except (TypeError, ValueError):
                    out[col] = None
    return out


def _merge_eval_config(
    out_dir: Path,
    run_id: str,
    llm_provider: str,
    quick: str,
    deep: str,
    backend_url: Optional[str],
    max_recur_limit: int,
) -> Dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    cfg["llm_provider"] = llm_provider
    cfg["quick_think_llm"] = quick
    cfg["deep_think_llm"] = deep
    if backend_url:
        cfg["backend_url"] = backend_url
    cfg["checkpoint_enabled"] = False
    cfg["max_recur_limit"] = max_recur_limit
    # Match CLI "Shallow" research depth (see cli/utils.py DEPTH_OPTIONS: 1=shallow, 3=medium, 5=deep).
    cfg["max_debate_rounds"] = 1
    cfg["max_risk_discuss_rounds"] = 1
    cfg["results_dir"] = str(out_dir / "ta_results")
    cfg["memory_log_path"] = str(out_dir / "memory" / f"batch_{run_id}.md")
    cfg["eval_strict_temporal"] = True
    return cfg


def _load_rubric_scores(path: Optional[Path]) -> Optional[Dict[str, float]]:
    """Load aggregate rubric dimension scores (0-2) from a JSON file, if present.

    Wires :func:`weighted_rubric_score` into the batch summary so process-quality
    (not just outcome alpha) is tracked. The file is optional; absence is fine.
    """
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    scores = data.get("scores", data) if isinstance(data, dict) else None
    if not isinstance(scores, dict):
        return None
    out: Dict[str, float] = {}
    for k, v in scores.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out or None


def _summarize(
    rows: List[Dict[str, Any]],
    horizons: List[int],
    rubric_scores: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Rich prediction-quality summary (accuracy, confusion, baselines, CIs)."""
    from tradingagents.evaluation.metrics import summarize_predictions

    return summarize_predictions(rows, horizons, rubric_scores=rubric_scores)


def _append_eval_history(
    history_path: Path,
    run_id: str,
    meta: Dict[str, Any],
    summary: Dict[str, Any],
    horizons: List[int],
) -> None:
    """Append one row per run to a longitudinal eval_history.csv.

    Lets you track whether predictions improve over time across prompt/model
    versions, instead of only inspecting a single run's summary in isolation.
    """
    from datetime import datetime, timezone

    header = [
        "run_id",
        "timestamp_utc",
        "universe_file",
        "llm_provider",
        "quick_think_llm",
        "deep_think_llm",
        "prompt_version",
        "n_rows",
        "n_ok_runs",
        "n_rating_parse_failures",
        "n_structured_fallbacks",
        "rubric_weighted_score",
    ]
    for h in horizons:
        header.extend(
            [
                f"directional_accuracy_{h}d",
                f"long_short_alpha_{h}d",
                f"sharpe_like_{h}d",
            ]
        )

    row: Dict[str, Any] = {
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "universe_file": meta.get("universe_file", ""),
        "llm_provider": meta.get("llm_provider", ""),
        "quick_think_llm": meta.get("quick_think_llm", ""),
        "deep_think_llm": meta.get("deep_think_llm", ""),
        "prompt_version": meta.get("prompt_version", ""),
        "n_rows": summary.get("n_rows", 0),
        "n_ok_runs": summary.get("n_ok_runs", 0),
        "n_rating_parse_failures": summary.get("n_rating_parse_failures", 0),
        "n_structured_fallbacks": summary.get("n_structured_fallbacks", 0),
        "rubric_weighted_score": summary.get("rubric_weighted_score", ""),
    }
    for h in horizons:
        block = summary.get("horizons", {}).get(str(h), {})
        row[f"directional_accuracy_{h}d"] = block.get("directional_accuracy", "")
        row[f"long_short_alpha_{h}d"] = block.get("long_short_alpha", "")
        row[f"sharpe_like_{h}d"] = block.get("sharpe_like", "")

    history_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not history_path.exists()
    with open(history_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerow(row)


def main() -> int:
    p = argparse.ArgumentParser(description="TradingAgents long-horizon pipeline eval batch runner")
    p.add_argument(
        "--universe",
        type=Path,
        default=_ROOT / "tradingagents/evaluation/universe_lt_eval.json",
        help="JSON file with anchors, tickers, horizons_calendar_days, benchmark_ticker",
    )
    p.add_argument("--out", type=Path, default=Path("pipeline_eval_out"), help="Output directory")
    p.add_argument("--preflight-only", action="store_true", help="Only run Yahoo/preflight checks")
    p.add_argument("--run-date", type=str, default=None, help="ISO date for observability cutoff (default: today)")
    p.add_argument("--llm-provider", type=str, default="ollama")
    p.add_argument("--quick-model", type=str, default="gemma4:31b-cloud")
    p.add_argument("--deep-model", type=str, default="gemma4:31b-cloud")
    p.add_argument("--backend-url", type=str, default=None)
    p.add_argument("--max-recur-limit", type=int, default=400)
    p.add_argument(
        "--workers",
        type=int,
        default=max(2, min(4, (os.cpu_count() or 4))),
        help="Parallel process count for full runs (each job isolated; 1 = sequential).",
    )
    p.add_argument("--skip-rubric-artifacts", action="store_true")
    p.add_argument(
        "--prompt-version",
        type=str,
        default="",
        help="Free-form prompt/config version tag recorded in metadata and eval_history.csv.",
    )
    p.add_argument(
        "--eval-history",
        type=Path,
        default=None,
        help="Path to a longitudinal eval_history.csv (default: <out>/../eval_history.csv).",
    )
    p.add_argument(
        "--rubric-scores",
        type=Path,
        default=None,
        help="Optional JSON of aggregate rubric dimension scores (0-2) to fold into the summary.",
    )
    p.add_argument(
        "--resume-from",
        type=Path,
        default=None,
        help="Existing eval_results.csv: rerun only rows with errors / empty rating; keep others.",
    )
    args = p.parse_args()

    universe = _load_universe(args.universe)
    anchors = universe["anchors"]
    tickers = [str(t).strip().upper() for t in universe["tickers"]]
    horizons = [int(h) for h in universe.get("horizons_calendar_days", [60, 365, 1095])]
    benchmark = universe.get("benchmark_ticker", "SPY")

    run_date = date.fromisoformat(args.run_date) if args.run_date else date.today()
    run_id = uuid.uuid4().hex[:12]
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    preflight_rows = preflight_pairs(tickers, anchors, horizons, benchmark, run_date=run_date)
    preflight_json = preflight_report(preflight_rows)
    (out_dir / "preflight_report.json").write_text(json.dumps(preflight_json, indent=2), encoding="utf-8")

    if args.preflight_only:
        print(json.dumps(preflight_json, indent=2))
        # Do not treat "horizon not yet observable" as a hard failure (expected for recent anchors).
        hard_fail = any(
            not r["ok"] and "not yet observable" not in r["detail"]
            for r in preflight_json["rows"]
        )
        return 2 if hard_fail else 0

    base_cfg = _merge_eval_config(
        out_dir,
        run_id,
        args.llm_provider,
        args.quick_model,
        args.deep_model,
        args.backend_url,
        args.max_recur_limit,
    )

    meta_path = out_dir / "run_metadata.json"
    meta_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "universe_file": str(args.universe),
                "llm_provider": args.llm_provider,
                "quick_think_llm": args.quick_model,
                "deep_think_llm": args.deep_model,
                "backend_url": args.backend_url,
                "benchmark_ticker": benchmark,
                "horizons_calendar_days": horizons,
                "anchors": anchors,
                "tickers": tickers,
                "observable_through": str(run_date),
                "eval_workers": args.workers,
                "research_depth": "shallow",
                "max_debate_rounds": 1,
                "max_risk_discuss_rounds": 1,
                "eval_strict_temporal": True,
                "prompt_version": args.prompt_version,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    if not args.skip_rubric_artifacts:
        write_offline_rubric_pack(out_dir)

    csv_path = out_dir / "eval_results.csv"
    fieldnames = [
        "ticker",
        "trade_date",
        "rating",
        "rating_bucket",
        # Rich signal extracted from the structured PM decision (Phase 2).
        "rating_score",
        "directional_score",
        "confidence",
        "price_target",
        "time_horizon",
        "bull_case_target",
        "base_case_target",
        "bear_case_target",
        "bull_probability",
        "base_probability",
        "bear_probability",
        "trader_action",
        "decision_consistency",
        "rating_parse_failed",
        "structured_fallback_used",
        # Point-in-time momentum baseline input.
        "prior_return_trailing",
        "error",
        "llm_provider",
        "quick_think_llm",
        "deep_think_llm",
    ]
    for h in horizons:
        fieldnames.extend([f"raw_return_{h}d", f"alpha_return_{h}d"])

    rows_out: List[Dict[str, Any]] = []
    kept_rows: List[Dict[str, Any]] = []
    rerun_keys: set = set()

    if args.resume_from is not None:
        prior = _load_existing_csv(args.resume_from.resolve())
        for prior_row in prior:
            key = (prior_row.get("ticker", "").strip().upper(), prior_row.get("trade_date", "").strip())
            if not key[0] or not key[1]:
                continue
            if _row_needs_rerun(prior_row):
                rerun_keys.add(key)
            else:
                kept_rows.append(_coerce_csv_floats(prior_row, horizons))
        if not rerun_keys:
            print(f"--resume-from: no failed rows in {args.resume_from}. Nothing to do.")
            # Still rewrite outputs with the prior data for consistency.
            rows_out = kept_rows
        else:
            print(f"--resume-from: {len(rerun_keys)} row(s) need rerun: {sorted(rerun_keys)}")

    jobs: List[Dict[str, Any]] = []
    for anchor in anchors:
        for ticker in tickers:
            if args.resume_from is not None and (ticker, anchor) not in rerun_keys:
                continue
            cfg = base_cfg.copy()
            cfg["memory_log_path"] = str(
                out_dir / "memory" / f"{ticker}_{anchor.replace('-', '')}_{run_id}.md"
            )
            jobs.append(
                {
                    "root": str(_ROOT),
                    "config": cfg,
                    "ticker": ticker,
                    "anchor": anchor,
                    "horizons": horizons,
                    "benchmark": benchmark,
                    "run_date_iso": run_date.isoformat(),
                    "llm_provider": args.llm_provider,
                    "quick_think_llm": args.quick_model,
                    "deep_think_llm": args.deep_model,
                }
            )

    new_rows: List[Dict[str, Any]] = []
    if args.workers <= 1:
        for job in jobs:
            new_rows.append(run_single_pipeline_eval(job))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(run_single_pipeline_eval, j): j for j in jobs}
            for fut in as_completed(futures):
                new_rows.append(fut.result())

    rows_out = kept_rows + new_rows
    rows_out.sort(key=lambda r: (r["trade_date"], r["ticker"]))

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows_out:
            w.writerow(row)

    rubric_scores = _load_rubric_scores(args.rubric_scores)
    summary = _summarize(rows_out, horizons, rubric_scores=rubric_scores)
    (out_dir / "eval_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    history_path = args.eval_history or (out_dir.parent / "eval_history.csv")
    _append_eval_history(history_path, run_id, meta, summary, horizons)

    print(f"Wrote {csv_path} ({len(rows_out)} rows)")
    print(f"Appended run summary to {history_path}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
