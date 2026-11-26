from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

from tradingagents.evaluation.portfolio_metrics import summarize_portfolio
from tradingagents.evaluation.portfolio_policy import target_weights
from tradingagents.evaluation.portfolio_simulator import PortfolioSimulator


def test_policy_hold_does_not_initiate_and_preserves_existing():
    signals = {"A": {"rating": "Hold"}, "B": {"rating": "Buy"}, "C": {"rating": "Overweight"}}
    targets = target_weights(signals, {"A": 0.1}, {"A": 0, "B": 0, "C": 0})
    assert targets["A"] == pytest.approx(0.1)
    assert targets["B"] == pytest.approx(0.2)
    assert targets["C"] == pytest.approx(0.2)
    assert sum(targets.values()) == pytest.approx(0.5)


def test_policy_invalid_and_expired_exit():
    signals = {
        "A": {"rating": "Buy", "rating_parse_failed": "true"},
        "B": {"rating": "Buy"},
        "C": {"rating": "Sell"},
    }
    targets = target_weights(signals, {"A": 0.2, "B": 0.2, "C": 0.2}, {"A": 0, "B": 21, "C": 0})
    assert all(weight == 0 for weight in targets.values())


def test_simulator_fractional_fill_costs_and_conservation():
    sim = PortfolioSimulator(initial_cash=100, slippage_bps=10)
    sim.rebalance("2020-01-02", {"A": 0.2}, {"A": 10})
    assert 0 < sim.positions["A"] <= 2
    assert sim.cash >= 0
    assert sim.equity({"A": 10}) == pytest.approx(100 - sim.total_costs)
    sim.rebalance("2020-01-03", {"A": 0.0}, {"A": 11})
    assert "A" not in sim.positions
    assert sim.cash > 100
    assert all(fill["quantity"] > 0 for fill in sim.fills)


def test_portfolio_metrics_known_path():
    rows = [
        {"equity": 100, "gross_exposure": 50},
        {"equity": 110, "gross_exposure": 55},
        {"equity": 99, "gross_exposure": 0},
    ]
    out = summarize_portfolio(rows, initial_cash=100)
    assert out["terminal_wealth"] == 99
    assert out["total_return"] == pytest.approx(-0.01)
    assert out["max_drawdown"] == pytest.approx(-0.10)


def _write_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_stage_a_runner_writes_auditable_outputs(tmp_path: Path):
    spec = importlib.util.spec_from_file_location("run_portfolio_eval", Path("scripts/run_portfolio_eval.py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    signals = tmp_path / "signals.csv"
    prices = tmp_path / "prices.csv"
    _write_csv(signals, [
        {"trade_date": "2020-01-01", "ticker": "A", "rating": "Buy"},
        {"trade_date": "2020-01-08", "ticker": "A", "rating": "Hold"},
        {"trade_date": "2020-01-15", "ticker": "A", "rating": "Sell"},
    ])
    _write_csv(prices, [
        {"date": "2020-01-02", "ticker": "A", "open": 10, "close": 10},
        {"date": "2020-01-09", "ticker": "A", "open": 11, "close": 11},
        {"date": "2020-01-16", "ticker": "A", "open": 12, "close": 12},
        {"date": "2020-01-17", "ticker": "A", "open": 12, "close": 12},
    ])
    protocol = tmp_path / "protocol.json"
    base = json.loads(Path("tradingagents/evaluation/portfolio_protocol_v1.json").read_text())
    protocol.write_text(json.dumps(base))
    out_dir = tmp_path / "out"
    summary = module.run_evaluation(signals, prices, out_dir, protocol, min_dates=12)
    assert summary["verdict"] == "INCONCLUSIVE"
    assert summary["strategy"]["terminal_wealth"] > 100
    for name in ("signals.csv", "orders.csv", "fills.csv", "positions.csv", "equity_curve.csv", "portfolio_summary.json", "REPORT.md"):
        assert (out_dir / name).exists()
