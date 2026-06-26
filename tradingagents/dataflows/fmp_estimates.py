"""Point-in-time analyst estimates & price targets (Financial Modeling Prep).

Yahoo's analyst estimates are a live snapshot, which strict eval mode drops to
avoid look-ahead. FMP exposes dated estimate and price-target rows, so we can
filter to the latest record on or before the trade date -- a bias-free
consensus signal usable in historical backtests. Requires an FMP API key;
degrades gracefully (DataVendorSkipped) so the router falls through to Yahoo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from tradingagents.dataflows.api_file_cache import cache_get_json, cache_set_json
from tradingagents.dataflows.config import DataVendorSkipped
from tradingagents.dataflows.fmp_transcripts import _api_key, _fmp_symbol

_BASE = "https://financialmodelingprep.com/stable"


def _get_json(url: str, params: Dict[str, Any]) -> Any:
    r = requests.get(url, params=params, timeout=45)
    r.raise_for_status()
    return r.json()


def _on_or_before(rows: List[Dict[str, Any]], curr_date: str, field: str = "date") -> List[Dict[str, Any]]:
    cut = datetime.strptime(curr_date, "%Y-%m-%d")
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw = row.get(field) or row.get("publishedDate") or ""
        if not raw:
            continue
        try:
            d = datetime.strptime(str(raw)[:10], "%Y-%m-%d")
        except ValueError:
            continue
        if d <= cut:
            out.append(row)
    return out


def _revision_note(latest: Dict[str, Any], prior: Optional[Dict[str, Any]]) -> List[str]:
    if not prior:
        return ["- Estimate revision: insufficient prior dated row for drift comparison."]
    lines = ["", "## Estimate revision drift (latest vs prior dated row)"]
    for field, label in (
        ("epsAvg", "EPS avg"),
        ("revenueAvg", "Revenue avg"),
        ("ebitdaAvg", "EBITDA avg"),
    ):
        cur = latest.get(field)
        old = prior.get(field)
        if cur is None or old is None:
            continue
        try:
            cur_f, old_f = float(cur), float(old)
            if old_f == 0:
                continue
            pct = (cur_f - old_f) / abs(old_f) * 100
            direction = "up" if pct > 0.5 else "down" if pct < -0.5 else "flat"
            lines.append(f"- {label}: {old_f:.4g} -> {cur_f:.4g} ({direction}, {pct:+.1f}%)")
        except (TypeError, ValueError):
            continue
    return lines


def _grades_summary(rows: List[Dict[str, Any]], curr_date: str) -> List[str]:
    eligible = _on_or_before(rows, curr_date, field="date")
    if not eligible:
        return []
    eligible.sort(key=lambda r: str(r.get("date", "")), reverse=True)
    latest = eligible[0]
    return [
        "",
        "## Recent analyst grade (FMP)",
        f"- Date: {latest.get('date', 'N/A')}",
        f"- Grade: {latest.get('newGrade', latest.get('gradingCompany', 'N/A'))}",
        f"- Previous grade: {latest.get('previousGrade', 'N/A')}",
        f"- Action: {latest.get('action', 'N/A')}",
    ]


def get_analyst_estimates_fmp(ticker: str, curr_date: str) -> str:
    """Latest dated analyst estimates and price-target consensus on/before trade date."""
    key = _api_key()
    if not key:
        raise DataVendorSkipped("FMP_API_KEY (or FINANCIAL_MODELING_PREP_API_KEY) not set")

    try:
        datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError as exc:
        return f"Invalid curr_date for analyst estimates: {curr_date} ({exc})"

    sym = _fmp_symbol(ticker)
    cache_key = f"fmp_estimates_{sym}_{curr_date}"
    cached = cache_get_json("fmp", cache_key, ttl_seconds=24 * 3600)
    if cached is None:
        try:
            estimates = _get_json(
                f"{_BASE}/analyst-estimates",
                {"symbol": sym, "period": "annual", "apikey": key},
            )
            targets = _get_json(
                f"{_BASE}/price-target-summary",
                {"symbol": sym, "apikey": key},
            )
            grades = _get_json(
                f"{_BASE}/grades-historical",
                {"symbol": sym, "apikey": key},
            )
        except requests.RequestException as exc:
            raise DataVendorSkipped(f"FMP estimates request failed: {exc}") from exc
        if isinstance(estimates, dict) and estimates.get("Error Message"):
            raise DataVendorSkipped(str(estimates.get("Error Message")))
        payload = {"estimates": estimates, "targets": targets, "grades": grades}
        cache_set_json("fmp", cache_key, payload)
    else:
        payload = cached

    estimates = payload.get("estimates") or []
    targets = payload.get("targets") or []
    grades = payload.get("grades") or []
    if not isinstance(estimates, list):
        estimates = []
    if not isinstance(grades, list):
        grades = []

    eligible = _on_or_before(estimates, curr_date)
    lines = [
        f"# Analyst estimates & price targets ({sym})",
        f"As of trade date: {curr_date}",
        "Source: Financial Modeling Prep (point-in-time; rows dated on/before trade date)",
        "",
    ]
    if not eligible:
        lines.append("No dated estimate rows on or before trade date.")
    else:
        eligible.sort(key=lambda r: str(r.get("date", "")), reverse=True)
        latest = eligible[0]
        prior = eligible[1] if len(eligible) > 1 else None
        lines.extend(
            [
                "## Latest consensus estimate (on/before trade date)",
                f"- Fiscal date: {latest.get('date', 'N/A')}",
                f"- Estimated revenue (avg): {latest.get('revenueAvg', 'N/A')}",
                f"- Estimated EPS (avg): {latest.get('epsAvg', 'N/A')}",
                f"- Estimated EBITDA (avg): {latest.get('ebitdaAvg', 'N/A')}",
                f"- Number of analysts (revenue): {latest.get('numAnalystsRevenue', 'N/A')}",
            ]
        )
        lines.extend(_revision_note(latest, prior))

    if isinstance(grades, list) and grades:
        lines.extend(_grades_summary(grades, curr_date))

    if isinstance(targets, list) and targets:
        t = targets[0]
        lines.extend(
            [
                "",
                "## Price-target summary",
                f"- Last month avg target: {t.get('lastMonthAvgPriceTarget', t.get('lastMonth', 'N/A'))}",
                f"- Last quarter avg target: {t.get('lastQuarterAvgPriceTarget', t.get('lastQuarter', 'N/A'))}",
                f"- All-time avg target: {t.get('allTimeAvgPriceTarget', 'N/A')}",
            ]
        )
    lines.extend(
        [
            "",
            "## How to use",
            "- Compare consensus drift over time; a thesis that needs estimates to rise is fragile if they are falling.",
            "- Treat price targets as anchors, not forecasts; weigh dispersion and analyst count.",
        ]
    )
    return "\n".join(lines)
