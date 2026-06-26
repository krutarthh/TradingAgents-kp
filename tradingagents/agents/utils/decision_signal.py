"""Build a rich, machine-readable signal from the Portfolio Manager decision.

The Portfolio Manager already produces a full ``PortfolioDecision`` (rating,
price targets, scenario targets, scenario probabilities, time horizon), but the
operational pipeline historically collapsed all of that into a single 5-tier
word. This module captures the full signal so downstream consumers (eval
harness, calibration, ranking, position sizing) can use it.

It supports two inputs:

- ``signal_from_decision`` — the authoritative path, fed the typed Pydantic
  instance straight from structured output (no lossy re-parsing).
- ``signal_from_markdown`` — a best-effort fallback for the free-text path,
  which flags ``rating_parse_failed`` when no rating can be recovered.

It also reconciles the Trader's 3-tier action with the PM's 5-tier rating so a
silent divergence (e.g. Trader says Sell, PM says Buy) is surfaced rather than
hidden.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from tradingagents.agents.utils.rating import (
    RATING_SCORE,
    parse_rating_with_status,
    rating_bucket,
)


def _directional_score(bull_p: float, bear_p: float) -> float:
    """Continuous conviction in [-1, 1]: skew of scenario probability mass."""
    return round(bull_p - bear_p, 4)


def _confidence(bull_p: float, base_p: float, bear_p: float) -> float:
    """Confidence as the largest scenario probability (peakedness of the view)."""
    return round(max(bull_p, base_p, bear_p), 4)


def signal_from_decision(decision: Any) -> Dict[str, Any]:
    """Build the rich signal dict from a typed PortfolioDecision instance."""
    rating = decision.rating.value
    bucket = rating_bucket(rating)
    bull_p = float(decision.bull_probability)
    base_p = float(decision.base_probability)
    bear_p = float(decision.bear_probability)
    return {
        "rating": rating,
        "rating_bucket": bucket,
        "rating_score": RATING_SCORE.get(rating.lower(), 0),
        "directional_score": _directional_score(bull_p, bear_p),
        "confidence": _confidence(bull_p, base_p, bear_p),
        "price_target": decision.price_target,
        "time_horizon": decision.time_horizon,
        "bull_case_target": decision.bull_case_target,
        "base_case_target": decision.base_case_target,
        "bear_case_target": decision.bear_case_target,
        "bull_probability": bull_p,
        "base_probability": base_p,
        "bear_probability": bear_p,
        "rating_parse_failed": False,
        "structured_fallback_used": False,
    }


_NUM_RE = r"([-+]?\d[\d,]*\.?\d*)"


def _find_float(label: str, text: str) -> Optional[float]:
    m = re.search(rf"\*\*{label}\*\*:\s*{_NUM_RE}", text, re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _find_scenario_probs(text: str) -> Optional[Dict[str, float]]:
    m = re.search(
        r"Bull=([0-9.]+),\s*Base=([0-9.]+),\s*Bear=([0-9.]+)",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    try:
        return {
            "bull": float(m.group(1)),
            "base": float(m.group(2)),
            "bear": float(m.group(3)),
        }
    except ValueError:
        return None


def signal_from_markdown(markdown: str) -> Dict[str, Any]:
    """Best-effort signal from rendered/free-text PM markdown (fallback path).

    Flags ``rating_parse_failed`` when no rating word can be recovered, so a
    missing rating is never silently bucketed as a (false) neutral Hold.
    """
    text = markdown or ""
    rating, found = parse_rating_with_status(text)
    bucket = rating_bucket(rating) if found else "unparsed"
    probs = _find_scenario_probs(text)
    bull_p = probs["bull"] if probs else None
    base_p = probs["base"] if probs else None
    bear_p = probs["bear"] if probs else None

    signal: Dict[str, Any] = {
        "rating": rating if found else "",
        "rating_bucket": bucket,
        "rating_score": RATING_SCORE.get((rating or "").lower(), 0) if found else None,
        "directional_score": (
            _directional_score(bull_p, bear_p) if bull_p is not None and bear_p is not None else None
        ),
        "confidence": (
            _confidence(bull_p, base_p, bear_p)
            if None not in (bull_p, base_p, bear_p)
            else None
        ),
        "price_target": _find_float("Price Target", text),
        "time_horizon": None,
        "bull_case_target": None,
        "base_case_target": None,
        "bear_case_target": None,
        "bull_probability": bull_p,
        "base_probability": base_p,
        "bear_probability": bear_p,
        "rating_parse_failed": not found,
        "structured_fallback_used": True,
    }
    return signal


_BULLISH_ACTIONS = {"buy"}
_BEARISH_ACTIONS = {"sell"}


def _action_direction(action: str) -> str:
    a = (action or "").strip().lower()
    if a in _BULLISH_ACTIONS:
        return "bullish"
    if a in _BEARISH_ACTIONS:
        return "bearish"
    return "neutral"


def reconcile_trader_pm(trader_action: Optional[str], pm_bucket: str) -> str:
    """Compare the Trader's 3-tier action direction with the PM's 5-tier bucket.

    Returns one of:
    - ``consistent``     — same direction
    - ``inconsistent``   — opposite direction (e.g. Trader Sell vs PM Buy)
    - ``divergent``      — one neutral, one directional
    - ``unknown``        — trader action missing/unparseable
    """
    if not trader_action:
        return "unknown"
    trader_dir = _action_direction(trader_action)
    if pm_bucket not in ("bullish", "bearish", "neutral"):
        return "unknown"
    if trader_dir == pm_bucket:
        return "consistent"
    if {trader_dir, pm_bucket} == {"bullish", "bearish"}:
        return "inconsistent"
    return "divergent"


def extract_trader_action(trader_markdown: str) -> Optional[str]:
    """Pull the Trader's Buy/Hold/Sell action from its rendered markdown."""
    text = trader_markdown or ""
    m = re.search(r"\*\*Action\*\*:\s*(\w+)", text, re.IGNORECASE)
    if m and m.group(1).lower() in ("buy", "hold", "sell"):
        return m.group(1).capitalize()
    m = re.search(r"FINAL TRANSACTION PROPOSAL:\s*\*\*(\w+)\*\*", text, re.IGNORECASE)
    if m and m.group(1).lower() in ("buy", "hold", "sell"):
        return m.group(1).capitalize()
    return None
