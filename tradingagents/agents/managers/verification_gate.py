"""Cheap structural checks on analyst outputs before the Research Manager."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from tradingagents.dataflows.config import get_config


def _scenario_probability_notes(text: str) -> List[str]:
    notes = []
    if not text or "## Bull" not in text and "bull" not in text.lower():
        return notes
    nums = re.findall(r"\b(\d{1,2}(?:\.\d+)?)\s*%", text)
    if len(nums) >= 3:
        try:
            total = sum(float(x) for x in nums[:6]) / 100.0
            if total < 0.85 or total > 1.15:
                notes.append(
                    f"forward_report scenario % values sum roughly {total:.2f} — confirm bull/base/bear probabilities are intentional"
                )
        except ValueError:
            pass
    return notes


def create_verification_gate():
    """Rules-only verifier before Research Manager."""

    def verification_gate_node(state: Dict[str, Any]) -> dict:
        if not get_config().get("enable_verification_gate", True):
            return {"verification_notes": "(verification gate disabled in config)"}

        notes: List[str] = []
        integ = state.get("integrated_thesis_report") or ""
        if not integ.strip():
            notes.append("integrated_thesis_report is empty")
        else:
            low = integ.lower()
            digest_mode = "thesis integrator llm disabled" in low
            headings_ok = "## unified thesis" in low
            if not headings_ok:
                notes.append("missing heading in integrated thesis: ## Unified thesis")
            if not digest_mode:
                for heading in (
                    "## Cross-report conflicts",
                    "## Valuation non-negotiables",
                ):
                    if heading.lower() not in low:
                        notes.append(f"missing heading in integrated thesis: {heading}")

        fwd = state.get("forward_report") or ""
        notes.extend(_scenario_probability_notes(fwd))

        for label, key in (
            ("Market", "market_report"),
            ("Fundamentals", "fundamentals_report"),
            ("Forward", "forward_report"),
        ):
            body = state.get(key) or ""
            if body and "## Executive Summary" not in body:
                notes.append(f"{label} report may be missing '## Executive Summary' heading")

        if not notes:
            summary = "OK: no structural issues flagged by verifier-lite."
        else:
            summary = "Verifier-lite notes:\n- " + "\n- ".join(notes)

        return {"verification_notes": summary}

    return verification_gate_node
