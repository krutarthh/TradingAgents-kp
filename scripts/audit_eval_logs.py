#!/usr/bin/env python3
"""Scan eval state logs for likely temporal leakage markers."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


LEAK_PATTERNS = [
    (re.compile(r"Data retrieved on:\s*20(1[89]|2[0-9])", re.I), "live retrieval header"),
    (re.compile(r"targetMeanPrice|forwardPE|recommendationKey", re.I), "live yfinance info field"),
    (re.compile(r"CNN Fear & Greed Index snapshot", re.I), "live fear/greed in log"),
]


def audit_file(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"{path}: unreadable ({exc})"]

    blob = json.dumps(data)
    for pattern, label in LEAK_PATTERNS:
        if pattern.search(blob):
            issues.append(f"{path.name}: {label}")
    return issues


def main() -> int:
    p = argparse.ArgumentParser(description="Audit eval full_states_log JSON for leakage hints")
    p.add_argument(
        "root",
        type=Path,
        nargs="?",
        default=Path("eval_out_crisis/ta_results"),
        help="Root directory containing ticker subfolders",
    )
    args = p.parse_args()
    root = args.root.resolve()
    if not root.exists():
        print(f"No directory: {root}", file=sys.stderr)
        return 2

    all_issues: list[str] = []
    for log_path in sorted(root.glob("**/full_states_log_*.json")):
        all_issues.extend(audit_file(log_path))

    if not all_issues:
        print(f"No leakage markers found under {root}")
        return 0

    print(f"Found {len(all_issues)} potential issue(s):")
    for line in all_issues:
        print(f"  - {line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
