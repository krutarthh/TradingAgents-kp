"""Tests for multi-horizon forward return labels."""

from datetime import date
from unittest.mock import patch

import pytest

from tradingagents.evaluation.eval_loop import (
    compute_60d_label,
    compute_forward_return_label,
    join_forward_labels_for_tickers,
)


@pytest.mark.unit
def test_compute_forward_observable_gate_returns_none():
    """Forward horizon ending after observable_through must not fabricate labels."""
    anchor = "2025-05-12"
    # Force observable cutoff before anchor + 365
    cutoff = date(2025, 6, 1)
    assert compute_forward_return_label("AAPL", anchor, 365, observable_through=cutoff) is None


@pytest.mark.unit
def test_compute_60d_delegates_to_forward():
    with patch("tradingagents.evaluation.eval_loop.compute_forward_return_label") as mock_fwd:
        mock_fwd.return_value = {
            "horizon_days": 60.0,
            "raw_return": 0.1,
            "alpha_return": 0.02,
        }
        out = compute_60d_label("X", "2024-01-02")
        mock_fwd.assert_called_once()
        assert out == {"raw_return_60d": 0.1, "alpha_return_60d": 0.02}


@pytest.mark.unit
def test_join_forward_labels_keys():
    with patch("tradingagents.evaluation.eval_loop.compute_forward_return_label") as mock_fwd:
        mock_fwd.side_effect = [
            {"horizon_days": 60.0, "raw_return": 0.01, "alpha_return": 0.0},
            {"horizon_days": 365.0, "raw_return": 0.05, "alpha_return": 0.01},
        ]
        out = join_forward_labels_for_tickers("NVDA", "2020-05-12", [60, 365])
        assert out["raw_return_60d"] == 0.01
        assert out["alpha_return_365d"] == 0.01


@pytest.mark.unit
def test_preflight_horizon_observable():
    from tradingagents.evaluation.preflight import horizon_observable

    assert horizon_observable("2020-05-12", 365, date(2026, 1, 1))
    assert not horizon_observable("2025-05-12", 1095, date(2026, 5, 1))


@pytest.mark.unit
def test_write_offline_rubric_pack(tmp_path):
    from tradingagents.evaluation.rubric_batch import write_offline_rubric_pack

    p = write_offline_rubric_pack(tmp_path)
    assert p.exists()
    assert "Analysis framework rubric" in p.read_text(encoding="utf-8")
