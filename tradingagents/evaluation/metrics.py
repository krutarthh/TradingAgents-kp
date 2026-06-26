"""Prediction-quality metrics for the pipeline eval harness.

The batch runner records, per ``(ticker, anchor)`` row, a 5-tier rating plus
realized forward returns (raw and alpha vs the benchmark) at each horizon.
Historically the only summary number was "bullish calls with positive 365d
alpha", which ignores bearish/neutral calls, every other horizon, magnitude,
calibration, and gives no way to tell signal from noise.

This module turns the rows into rigorous, comparable metrics:

- Directional accuracy / hit rate per horizon (bullish->alpha>0, bearish->
  alpha<0, neutral->|alpha| within a band), with a full confusion matrix.
- Per-bucket (bullish/bearish/neutral) and per-5-tier breakdowns.
- Mean / median alpha and a magnitude-weighted long-short score (the alpha you
  would have captured by trading the signal), plus a cross-sectional Sharpe.
- Baselines (always-long, benchmark, random, momentum, analyst consensus) so a
  result is judged relative to trivial strategies, not in a vacuum.
- Bootstrap confidence intervals over rows so small-N runs report uncertainty.
- Multiclass Brier score / reliability of the PM scenario probabilities when
  they are present in the rows (calibration).

Everything is pure-Python and operates on already-collected rows, so it is
deterministic and unit-testable with no network access.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

# Canonical bucketing shared with the worker.
_BULLISH = {"buy", "overweight"}
_BEARISH = {"sell", "underweight"}

# Default band (in alpha return) within which a Hold is considered "correct"
# and a realized outcome is classified as the base/neutral case.
DEFAULT_HOLD_BAND = 0.05

# Rating -> ordinal conviction score (used for ranking and continuous analysis).
RATING_SCORE = {
    "buy": 2,
    "overweight": 1,
    "hold": 0,
    "underweight": -1,
    "sell": -2,
}


def rating_bucket(rating: Optional[str]) -> str:
    """Map a 5-tier rating to bullish / bearish / neutral."""
    r = (rating or "").strip().lower()
    if r in _BULLISH:
        return "bullish"
    if r in _BEARISH:
        return "bearish"
    return "neutral"


def bucket_direction(bucket: str) -> int:
    return {"bullish": 1, "bearish": -1}.get(bucket, 0)


def _to_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _alpha(row: Dict[str, Any], horizon: int) -> Optional[float]:
    return _to_float(row.get(f"alpha_return_{horizon}d"))


def _raw(row: Dict[str, Any], horizon: int) -> Optional[float]:
    return _to_float(row.get(f"raw_return_{horizon}d"))


def realized_class(alpha: float, hold_band: float) -> str:
    """Classify a realized alpha into bullish / bearish / neutral by a band."""
    if alpha > hold_band:
        return "bullish"
    if alpha < -hold_band:
        return "bearish"
    return "neutral"


def directional_correct(bucket: str, alpha: float, hold_band: float) -> bool:
    """A call is correct when its direction matches the realized alpha sign.

    Neutral (Hold) is correct only when the realized move is small (|alpha|
    within ``hold_band``) -- so Hold is finally scored instead of ignored.
    """
    if bucket == "bullish":
        return alpha > 0
    if bucket == "bearish":
        return alpha < 0
    return abs(alpha) <= hold_band


def signed_alpha(bucket: str, alpha: float) -> float:
    """Alpha captured by trading the signal (long bullish, short bearish)."""
    return bucket_direction(bucket) * alpha


def _safe_mean(values: Sequence[float]) -> Optional[float]:
    return statistics.fmean(values) if values else None


def _safe_median(values: Sequence[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def _sharpe_like(values: Sequence[float]) -> Optional[float]:
    """Mean / standard deviation of a cross-section of signed alphas."""
    if len(values) < 2:
        return None
    sd = statistics.pstdev(values)
    if sd == 0:
        return None
    return statistics.fmean(values) / sd


def _bucket_block(rows_alpha: List[tuple], hold_band: float) -> Dict[str, Any]:
    """Aggregate metrics for a set of (bucket, alpha) pairs."""
    n = len(rows_alpha)
    if n == 0:
        return {"n": 0}
    correct = sum(1 for b, a in rows_alpha if directional_correct(b, a, hold_band))
    alphas = [a for _, a in rows_alpha]
    signed = [signed_alpha(b, a) for b, a in rows_alpha]
    return {
        "n": n,
        "hit_rate": correct / n,
        "mean_alpha": _safe_mean(alphas),
        "median_alpha": _safe_median(alphas),
        "mean_signed_alpha": _safe_mean(signed),
    }


def _confusion_matrix(pairs: List[tuple], hold_band: float) -> Dict[str, Dict[str, int]]:
    """predicted bucket -> realized class -> count."""
    classes = ("bullish", "neutral", "bearish")
    matrix = {p: {r: 0 for r in classes} for p in classes}
    for bucket, alpha in pairs:
        matrix[bucket][realized_class(alpha, hold_band)] += 1
    return matrix


def _bootstrap_ci(
    pairs: List[tuple],
    hold_band: float,
    n_boot: int,
    seed: int,
) -> Dict[str, Any]:
    """Percentile bootstrap CIs for directional accuracy and long-short alpha."""
    if len(pairs) < 2 or n_boot <= 0:
        return {}
    rng = random.Random(seed)
    n = len(pairs)
    acc_samples: List[float] = []
    ls_samples: List[float] = []
    for _ in range(n_boot):
        sample = [pairs[rng.randrange(n)] for _ in range(n)]
        acc = sum(1 for b, a in sample if directional_correct(b, a, hold_band)) / n
        ls = statistics.fmean([signed_alpha(b, a) for b, a in sample])
        acc_samples.append(acc)
        ls_samples.append(ls)
    acc_samples.sort()
    ls_samples.sort()

    def _pct(sorted_vals: List[float], q: float) -> float:
        idx = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
        return sorted_vals[idx]

    return {
        "directional_accuracy_ci95": [_pct(acc_samples, 0.025), _pct(acc_samples, 0.975)],
        "long_short_alpha_ci95": [_pct(ls_samples, 0.025), _pct(ls_samples, 0.975)],
        "n_boot": n_boot,
    }


def _baselines(rows: List[Dict[str, Any]], horizon: int, hold_band: float) -> Dict[str, Any]:
    """Trivial-strategy baselines computed from the same rows.

    A model that cannot beat these is not adding value.
    """
    alphas = [a for a in (_alpha(r, horizon) for r in rows) if a is not None]
    out: Dict[str, Any] = {}
    if not alphas:
        return out

    n = len(alphas)
    frac_up = sum(1 for a in alphas if a > 0) / n
    frac_down = sum(1 for a in alphas if a < 0) / n
    frac_band = sum(1 for a in alphas if abs(a) <= hold_band) / n

    # Always-long: every name treated bullish.
    out["always_long"] = {
        "directional_accuracy": frac_up,
        "long_short_alpha": _safe_mean(alphas),
        "mean_alpha": _safe_mean(alphas),
    }

    # Benchmark buy-and-hold: alpha vs itself is 0 by construction; report the
    # benchmark's own raw return recovered as raw - alpha.
    bench_raw = [
        raw - a
        for raw, a in (
            (_raw(r, horizon), _alpha(r, horizon)) for r in rows
        )
        if raw is not None and a is not None
    ]
    out["benchmark_buy_hold"] = {
        "long_short_alpha": 0.0,
        "mean_raw_return": _safe_mean(bench_raw),
    }

    # Random 3-class assignment: expected accuracy is analytic (uniform over the
    # three buckets); expected long-short alpha is 0 (long and short cancel).
    out["random"] = {
        "directional_accuracy": (frac_up + frac_down + frac_band) / 3.0,
        "long_short_alpha": 0.0,
    }

    # Momentum: needs a point-in-time trailing return column from the worker.
    mom_pairs = []
    for r in rows:
        a = _alpha(r, horizon)
        trailing = _to_float(r.get("prior_return_trailing"))
        if a is None or trailing is None:
            continue
        bucket = "bullish" if trailing >= 0 else "bearish"
        mom_pairs.append((bucket, a))
    if mom_pairs:
        out["momentum"] = _bucket_block(mom_pairs, hold_band)
    else:
        out["momentum"] = {
            "available": False,
            "reason": "no 'prior_return_trailing' column on rows (worker did not record trailing momentum)",
        }

    # Analyst consensus: requires a point-in-time consensus signal column.
    cons_pairs = []
    for r in rows:
        a = _alpha(r, horizon)
        sig = (r.get("analyst_consensus_signal") or "").strip().lower()
        if a is None or sig not in ("bullish", "bearish", "neutral"):
            continue
        cons_pairs.append((sig, a))
    if cons_pairs:
        out["analyst_consensus"] = _bucket_block(cons_pairs, hold_band)
    else:
        out["analyst_consensus"] = {
            "available": False,
            "reason": "no point-in-time 'analyst_consensus_signal' column (needs a historical estimates connector)",
        }

    return out


def _calibration(rows: List[Dict[str, Any]], horizon: int, hold_band: float) -> Dict[str, Any]:
    """Multiclass Brier score + reliability of PM scenario probabilities.

    Requires ``bull_probability`` / ``base_probability`` / ``bear_probability``
    columns on the rows (populated from the structured PM decision). Returns an
    ``available: False`` block when they are absent.
    """
    briers: List[float] = []
    bull_probs: List[float] = []
    bull_outcomes: List[int] = []
    for r in rows:
        a = _alpha(r, horizon)
        pb = _to_float(r.get("bull_probability"))
        pbase = _to_float(r.get("base_probability"))
        pbear = _to_float(r.get("bear_probability"))
        if a is None or pb is None or pbase is None or pbear is None:
            continue
        cls = realized_class(a, hold_band)
        target = {
            "bullish": (1.0, 0.0, 0.0),
            "neutral": (0.0, 1.0, 0.0),
            "bearish": (0.0, 0.0, 1.0),
        }[cls]
        pred = (pb, pbase, pbear)
        briers.append(sum((p - t) ** 2 for p, t in zip(pred, target)))
        bull_probs.append(pb)
        bull_outcomes.append(1 if cls == "bullish" else 0)

    if not briers:
        return {
            "available": False,
            "reason": "no scenario-probability columns on rows (needs structured PM signal extraction)",
        }

    # Reliability: bin P(bull) into deciles, compare to realized bull frequency.
    bins: Dict[int, List[int]] = defaultdict(list)
    bin_probs: Dict[int, List[float]] = defaultdict(list)
    for p, o in zip(bull_probs, bull_outcomes):
        b = min(9, int(p * 10))
        bins[b].append(o)
        bin_probs[b].append(p)
    reliability = [
        {
            "bin": b / 10.0,
            "mean_predicted": _safe_mean(bin_probs[b]),
            "observed_freq": _safe_mean(bins[b]),
            "n": len(bins[b]),
        }
        for b in sorted(bins)
    ]
    return {
        "available": True,
        "n_scored": len(briers),
        "multiclass_brier": _safe_mean(briers),
        "bull_reliability": reliability,
    }


def horizon_metrics(
    rows: List[Dict[str, Any]],
    horizon: int,
    hold_band: float = DEFAULT_HOLD_BAND,
    n_boot: int = 1000,
    seed: int = 12345,
) -> Dict[str, Any]:
    """Full metric block for a single horizon."""
    pairs: List[tuple] = []  # (bucket, alpha)
    tier_pairs: Dict[str, List[tuple]] = defaultdict(list)
    bucket_pairs: Dict[str, List[tuple]] = defaultdict(list)
    for r in rows:
        if r.get("error"):
            continue
        a = _alpha(r, horizon)
        if a is None:
            continue
        rating = (r.get("rating") or "").strip()
        bucket = r.get("rating_bucket") or rating_bucket(rating)
        pairs.append((bucket, a))
        bucket_pairs[bucket].append((bucket, a))
        if rating:
            tier_pairs[rating].append((bucket, a))

    n = len(pairs)
    if n == 0:
        return {"n_scored": 0}

    correct = sum(1 for b, a in pairs if directional_correct(b, a, hold_band))
    alphas = [a for _, a in pairs]
    signed = [signed_alpha(b, a) for b, a in pairs]

    block: Dict[str, Any] = {
        "n_scored": n,
        "hold_band": hold_band,
        "directional_accuracy": correct / n,
        "mean_alpha": _safe_mean(alphas),
        "median_alpha": _safe_median(alphas),
        "long_short_alpha": _safe_mean(signed),
        "magnitude_weighted_score": _safe_mean(signed),
        "sharpe_like": _sharpe_like(signed),
        "confusion_matrix": _confusion_matrix(pairs, hold_band),
        "per_bucket": {b: _bucket_block(p, hold_band) for b, p in sorted(bucket_pairs.items())},
        "per_tier": {t: _bucket_block(p, hold_band) for t, p in sorted(tier_pairs.items())},
        "baselines": _baselines(rows, horizon, hold_band),
        "calibration": _calibration(rows, horizon, hold_band),
    }
    block.update(_bootstrap_ci(pairs, hold_band, n_boot, seed))
    return block


def _rating_distribution(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    dist: Dict[str, int] = defaultdict(int)
    for r in rows:
        if r.get("error"):
            continue
        bucket = r.get("rating_bucket") or rating_bucket(r.get("rating"))
        dist[bucket] += 1
    return dict(dist)


def _legacy_anchor_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Preserve the original per-anchor headline numbers for backward compat."""
    by_anchor: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_anchor[row.get("trade_date", "")].append(row)
    anchors: Dict[str, Any] = {}
    for anchor, rs in by_anchor.items():
        bullish = [r for r in rs if (r.get("rating_bucket") == "bullish") and not r.get("error")]
        alpha365_ok = [
            r for r in bullish
            if _alpha(r, 365) is not None and _alpha(r, 365) > 0
        ]
        anchors[anchor] = {
            "n_rows": len(rs),
            "n_ok_runs": sum(1 for r in rs if not r.get("error")),
            "bullish_count": len(bullish),
            "bullish_alpha365_positive_count": len(alpha365_ok),
        }
    return anchors


def summarize_predictions(
    rows: List[Dict[str, Any]],
    horizons: Sequence[int],
    hold_band: float = DEFAULT_HOLD_BAND,
    n_boot: int = 1000,
    seed: int = 12345,
    rubric_scores: Optional[Dict[str, float]] = None,
    rubric_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Top-level summary: rich per-horizon metrics + legacy anchor block."""
    summary: Dict[str, Any] = {
        "n_rows": len(rows),
        "n_ok_runs": sum(1 for r in rows if not r.get("error")),
        "n_errors": sum(1 for r in rows if r.get("error")),
        "n_rating_parse_failures": sum(
            1 for r in rows if str(r.get("rating_parse_failed", "")).strip().lower() in ("true", "1")
        ),
        "n_structured_fallbacks": sum(
            1 for r in rows if str(r.get("structured_fallback_used", "")).strip().lower() in ("true", "1")
        ),
        "rating_distribution": _rating_distribution(rows),
        "hold_band": hold_band,
        "horizons": {
            str(h): horizon_metrics(rows, int(h), hold_band, n_boot, seed)
            for h in horizons
        },
        "anchors": _legacy_anchor_summary(rows),
    }

    if rubric_scores:
        from tradingagents.evaluation.eval_loop import weighted_rubric_score

        summary["rubric_weighted_score"] = weighted_rubric_score(rubric_scores, rubric_weights)

    return summary
