#!/usr/bin/env python3
"""Review mature rows in the live shadow book and print prediction metrics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.evaluation.live_shadow_book import review_shadow_book


def main() -> None:
    parser = argparse.ArgumentParser(description="Review live shadow book metrics")
    parser.add_argument(
        "--path",
        default=DEFAULT_CONFIG.get("live_shadow_book_path"),
        help="Path to live_shadow_book.csv",
    )
    parser.add_argument(
        "--holding-days",
        type=int,
        default=int(DEFAULT_CONFIG.get("eval_holding_days", 60)),
        help="Forward return horizon in calendar days",
    )
    parser.add_argument(
        "--benchmark",
        default=DEFAULT_CONFIG.get("eval_benchmark_ticker", "SPY"),
        help="Benchmark ticker for alpha",
    )
    args = parser.parse_args()

    if not args.path:
        print("No shadow book path configured.", file=sys.stderr)
        sys.exit(1)

    report = review_shadow_book(
        args.path,
        holding_days=args.holding_days,
        benchmark=args.benchmark,
    )
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
