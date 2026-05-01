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


def _has_uncited_numbers(text: str) -> bool:
    if not text:
        return False
    has_number = bool(re.search(r"\b\d+(?:\.\d+)?%?\b", text))
    if not has_number:
        return False
    return "evidence" not in text.lower() and "tool=" not in text.lower()


def create_verification_gate():
    """Rules-only verifier before Research Manager."""

    def verification_gate_node(state: Dict[str, Any]) -> dict:
        if not get_config().get("enable_verification_gate", True):
            return {
                "verification_notes": "(verification gate disabled in config)",
                "verification_status": "pass",
            }

        notes: List[str] = []
        fails: List[str] = []
        integ = state.get("integrated_thesis_report") or ""
        if not integ.strip():
            fails.append("integrated_thesis_report is empty")
        else:
            low = integ.lower()
            digest_mode = "thesis integrator llm disabled" in low
            headings_ok = "## unified thesis" in low
            if not headings_ok:
                fails.append("missing heading in integrated thesis: ## Unified thesis")
            if not digest_mode:
                for heading in (
                    "## Cross-report conflicts",
                    "## Valuation non-negotiables",
                ):
                    if heading.lower() not in low:
                        fails.append(f"missing heading in integrated thesis: {heading}")

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
            if _has_uncited_numbers(body):
                notes.append(f"{label} report has numbers without clear citation/provenance text")

        if "valuation triangulation" not in (state.get("fundamentals_report") or "").lower():
            fails.append("fundamentals_report missing valuation triangulation section")
        if "valuation triangulation" not in (state.get("forward_report") or "").lower():
            fails.append("forward_report missing valuation triangulation section")

        status = "pass"
        if fails:
            status = "fail"
        elif notes:
            status = "warn"

        attempts = int(state.get("verification_attempts", 0) or 0)
        max_retries = int(get_config().get("verification_max_retries", 1) or 1)
        if status == "fail" and attempts >= max_retries:
            status = "warn"
            notes.append("max verification retries reached; downgrading fail to warn to continue pipeline")

        if not notes and not fails:
            summary = "OK: no structural issues flagged by verifier-plus."
        else:
            blocks: List[str] = []
            if fails:
                blocks.append("Fail checks:\n- " + "\n- ".join(fails))
            if notes:
                blocks.append("Warn checks:\n- " + "\n- ".join(notes))
            summary = "Verifier-plus findings:\n" + "\n\n".join(blocks)

        return {
            "verification_notes": summary,
            "verification_status": status,
            "verification_attempts": attempts + (1 if status == "fail" else 0),
        }

    return verification_gate_node
