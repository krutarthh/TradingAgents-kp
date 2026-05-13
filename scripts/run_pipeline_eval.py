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
from collections import defaultdict
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
    return cfg


def _summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_anchor: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_anchor[row["trade_date"]].append(row)

    summary: Dict[str, Any] = {"anchors": {}}
    for anchor, rs in by_anchor.items():
        bullish = [r for r in rs if r.get("rating_bucket") == "bullish" and not r.get("error")]
        alpha365_ok = [
            r
            for r in bullish
            if r.get("alpha_return_365d") is not None and float(r["alpha_return_365d"]) > 0
        ]
        summary["anchors"][anchor] = {
            "n_rows": len(rs),
            "n_ok_runs": sum(1 for r in rs if not r.get("error")),
            "bullish_count": len(bullish),
            "bullish_alpha365_positive_count": len(alpha365_ok),
        }
    return summary


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
        "error",
        "llm_provider",
        "quick_think_llm",
        "deep_think_llm",
    ]
    for h in horizons:
        fieldnames.extend([f"raw_return_{h}d", f"alpha_return_{h}d"])

    rows_out: List[Dict[str, Any]] = []

    jobs: List[Dict[str, Any]] = []
    for anchor in anchors:
        for ticker in tickers:
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

    if args.workers <= 1:
        for job in jobs:
            rows_out.append(run_single_pipeline_eval(job))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(run_single_pipeline_eval, j): j for j in jobs}
            for fut in as_completed(futures):
                rows_out.append(fut.result())

    rows_out.sort(key=lambda r: (r["trade_date"], r["ticker"]))

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows_out:
            w.writerow(row)

    summary = _summarize(rows_out)
    (out_dir / "eval_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {csv_path} ({len(rows_out)} rows)")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
