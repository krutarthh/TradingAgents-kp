#!/usr/bin/env python3
"""Run a deterministic shared-$100 portfolio evaluation from frozen CSV inputs.

Signals columns: trade_date,ticker,rating plus optional error/rating_parse_failed.
Prices columns: date,ticker,open,close. A signal made after ``trade_date`` close is
executed at the first later price date's open. Inputs are local and immutable;
this Stage-A runner makes no LLM or network calls.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tradingagents.evaluation.portfolio_metrics import summarize_portfolio
from tradingagents.evaluation.portfolio_policy import target_weights
from tradingagents.evaluation.portfolio_simulator import PortfolioSimulator


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _price_maps(rows: list[dict[str, str]]) -> tuple[list[str], dict[str, dict[str, dict[str, float]]]]:
    prices: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    for row in rows:
        prices[row["date"]][row["ticker"].upper()] = {
            "open": float(row["open"]), "close": float(row.get("close") or row["open"])
        }
    return sorted(prices), prices


def _next_date(dates: list[str], signal_date: str) -> str | None:
    return next((value for value in dates if value > signal_date), None)


def _buy_hold(initial_cash: float, first: dict[str, float], last: dict[str, float], tickers: list[str], bps: float) -> float | None:
    eligible = [t for t in tickers if t in first and t in last and first[t] > 0]
    if not eligible:
        return None
    sleeve = initial_cash / len(eligible)
    slip = bps / 10000.0
    return sum((sleeve / (first[t] * (1 + slip))) * last[t] for t in eligible)


def run_evaluation(
    signals_path: Path,
    prices_path: Path,
    out_dir: Path,
    protocol_path: Path,
    *,
    trusted_provenance: bool = False,
    min_dates: int = 12,
) -> dict[str, Any]:
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    signal_rows = _read_csv(signals_path)
    price_rows = _read_csv(prices_path)
    dates, prices = _price_maps(price_rows)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in signal_rows:
        grouped[row["trade_date"]].append(row)

    sim = PortfolioSimulator(
        initial_cash=float(protocol["initial_cash"]),
        commission=float(protocol["commission_per_fill"]),
        slippage_bps=float(protocol["slippage_bps"]),
    )
    latest: dict[str, dict[str, str]] = {}
    latest_index: dict[str, int] = {}
    normalized: list[dict[str, Any]] = []
    execution_dates: list[str] = []
    processed_signal_dates: list[str] = []

    for signal_date in sorted(grouped):
        execution_date = _next_date(dates, signal_date)
        if not execution_date:
            continue
        available = prices[execution_date]
        for row in grouped[signal_date]:
            ticker = row["ticker"].upper()
            latest[ticker] = dict(row, ticker=ticker)
            latest_index[ticker] = len(processed_signal_dates)
            normalized.append(dict(row, ticker=ticker, execution_date=execution_date))
        ages = {ticker: len(processed_signal_dates) - idx for ticker, idx in latest_index.items()}
        current_prices = {ticker: values["open"] for ticker, values in available.items()}
        current_weights = sim.weights(current_prices) if sim.equity_curve or sim.positions else {}
        targets = target_weights(
            latest, current_weights, ages,
            expiry_sessions=int(protocol["signal_expiry_trading_sessions"]),
            max_name_weight=float(protocol["max_name_weight"]),
        )
        required = set(targets) | set(sim.positions)
        if not required.issubset(current_prices):
            missing = sorted(required - set(current_prices))
            raise ValueError(f"missing execution prices on {execution_date}: {missing}")
        sim.rebalance(execution_date, targets, {t: current_prices[t] for t in required})
        execution_dates.append(execution_date)
        processed_signal_dates.append(signal_date)

    if dates and sim.positions:
        last_date = dates[-1]
        last_close = {t: p["close"] for t, p in prices[last_date].items() if t in sim.positions}
        if set(sim.positions).issubset(last_close):
            sim.mark(last_date, last_close)

    metrics = summarize_portfolio(
        sim.equity_curve, initial_cash=sim.initial_cash, total_costs=sim.total_costs,
        total_traded_notional=sim.total_traded_notional,
    )
    tickers = sorted({row["ticker"].upper() for row in signal_rows})
    first_exec = execution_dates[0] if execution_dates else None
    last_date = dates[-1] if dates else None
    matched_terminal = None
    spy_terminal = None
    if first_exec and last_date:
        first_open = {t: v["open"] for t, v in prices[first_exec].items()}
        last_close = {t: v["close"] for t, v in prices[last_date].items()}
        matched_terminal = _buy_hold(sim.initial_cash, first_open, last_close, tickers, sim.slippage_bps)
        spy_terminal = _buy_hold(sim.initial_cash, first_open, last_close, ["SPY"], sim.slippage_bps)

    parse_failures = sum(str(r.get("rating_parse_failed", "")).lower() in {"1", "true", "yes"} for r in signal_rows)
    errors = sum(bool((r.get("error") or "").strip()) for r in signal_rows)
    invalid_rate = (parse_failures + errors) / len(signal_rows) if signal_rows else 1.0
    reasons: list[str] = []
    verdict = "INCONCLUSIVE"
    if not trusted_provenance:
        reasons.append("signal/data provenance is not certified point-in-time")
    if len(processed_signal_dates) < min_dates:
        reasons.append(f"only {len(processed_signal_dates)} independent decision dates; require {min_dates}")
    if invalid_rate > 0.10:
        reasons.append(f"invalid/error signal rate {invalid_rate:.1%} exceeds 10%")
    if matched_terminal is None:
        reasons.append("matched buy-and-hold benchmark unavailable")
    if not reasons:
        if metrics["terminal_wealth"] > sim.initial_cash and metrics["terminal_wealth"] > matched_terminal:
            verdict = "PASS_RETROSPECTIVE"
            reasons.append("after-cost wealth is positive and beats matched buy-and-hold")
        else:
            verdict = "FAIL"
            reasons.append("strategy failed profitability and/or matched buy-and-hold hurdle")

    distribution = Counter((r.get("rating") or "unparsed").title() for r in signal_rows)
    summary = {
        "verdict": verdict, "reasons": reasons, "retrospective_only": True,
        "strategy": metrics,
        "benchmarks": {
            "matched_buy_hold_terminal_wealth": matched_terminal,
            "spy_terminal_wealth": spy_terminal,
            "cash_terminal_wealth": sim.initial_cash,
        },
        "diagnostics": {
            "n_signals": len(signal_rows), "n_decision_dates": len(processed_signal_dates),
            "rating_distribution": dict(distribution), "invalid_signal_rate": invalid_rate,
            "trusted_provenance": trusted_provenance,
        },
        "protocol_version": protocol["protocol_version"],
        "warning": protocol["historical_llm_warning"],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "protocol_snapshot.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    (out_dir / "portfolio_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_csv(out_dir / "signals.csv", normalized, sorted({k for r in normalized for k in r}) if normalized else ["trade_date", "ticker"])
    _write_csv(out_dir / "orders.csv", sim.orders, ["date", "ticker", "side", "quantity", "reference_price"])
    _write_csv(out_dir / "fills.csv", sim.fills, ["date", "ticker", "side", "quantity", "reference_price", "fill_price", "notional", "fee", "slippage_cost"])
    _write_csv(out_dir / "positions.csv", sim.positions_log, ["date", "ticker", "quantity", "price", "market_value", "weight"])
    _write_csv(out_dir / "equity_curve.csv", sim.equity_curve, ["date", "cash", "gross_exposure", "equity"])
    report = (
        "# Portfolio Evaluation\n\n"
        f"**Verdict: {verdict}**\n\n"
        f"Strategy: **${sim.initial_cash:.2f} → ${metrics['terminal_wealth']:.2f}** after costs.\n\n"
        f"Matched buy-and-hold: **${matched_terminal:.2f}**.\n\n" if matched_terminal is not None else "Matched buy-and-hold unavailable.\n\n"
    )
    report += "Reasons:\n" + "".join(f"- {reason}\n" for reason in reasons)
    report += "\n> Historical LLM replays are retrospective process tests, not proof of future profitability.\n"
    (out_dir / "REPORT.md").write_text(report, encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signals", type=Path, required=True)
    parser.add_argument("--prices", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("portfolio_eval_out"))
    parser.add_argument("--protocol", type=Path, default=_ROOT / "tradingagents/evaluation/portfolio_protocol_v1.json")
    parser.add_argument("--trusted-provenance", action="store_true")
    parser.add_argument("--min-dates", type=int, default=12)
    args = parser.parse_args()
    summary = run_evaluation(args.signals, args.prices, args.out, args.protocol, trusted_provenance=args.trusted_provenance, min_dates=args.min_dates)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
