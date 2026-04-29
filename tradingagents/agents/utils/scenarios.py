"""Scenario playbook used to force forward-looking analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class Scenario:
    name: str
    summary: str
    beneficiaries: List[str]
    pressured: List[str]
    key_tells: List[str]


SCENARIOS: Dict[str, Scenario] = {
    "AI_CAPEX_ACCELERATION": Scenario(
        name="AI_CAPEX_ACCELERATION",
        summary="Enterprise and hyperscaler AI spending accelerates faster than consensus.",
        beneficiaries=["Semiconductors", "Cloud", "Data Center Infra", "Cybersecurity", "Power Infrastructure"],
        pressured=["Traditional IT Services", "Labor-Intensive Business Models"],
        key_tells=["Raising capex guidance", "Strong GPU/networking lead times", "Higher power demand forecasts"],
    ),
    "AI_CAPEX_PULLBACK": Scenario(
        name="AI_CAPEX_PULLBACK",
        summary="AI spending normalizes after overbuild concerns and weaker ROI evidence.",
        beneficiaries=["Cash-generative Defensives", "Value Industrials"],
        pressured=["High-multiple AI proxies", "Unprofitable growth software", "Speculative compute themes"],
        key_tells=["Capex deferrals", "Model ROI skepticism", "Inventory build in AI supply chain"],
    ),
    "RATE_CUT_CYCLE": Scenario(
        name="RATE_CUT_CYCLE",
        summary="Central banks ease policy as inflation cools and growth slows modestly.",
        beneficiaries=["Long-duration growth", "Rate-sensitive real estate", "Small caps"],
        pressured=["Cash-like alternatives", "Banks with NIM pressure"],
        key_tells=["Falling real yields", "Dovish guidance", "Steeper policy easing path"],
    ),
    "RECESSION_HARD_LANDING": Scenario(
        name="RECESSION_HARD_LANDING",
        summary="Demand contracts sharply and earnings revisions turn broadly negative.",
        beneficiaries=["Defensive healthcare", "Utilities", "Quality balance-sheet compounders"],
        pressured=["Cyclicals", "High-beta growth", "Highly levered firms"],
        key_tells=["Rising unemployment", "PMI contraction", "Widening credit spreads"],
    ),
    "WAR_TAIWAN_ESCALATION": Scenario(
        name="WAR_TAIWAN_ESCALATION",
        summary="Taiwan Strait tensions escalate, disrupting supply chains and risk appetite.",
        beneficiaries=["Defense", "Energy security plays", "Domestic manufacturing themes"],
        pressured=["Semiconductor supply chain", "Global trade-sensitive names", "EM risk assets"],
        key_tells=["Sanctions escalation", "Shipping reroutes", "Policy coordination by major blocs"],
    ),
    "WAR_MIDEAST_OIL_SHOCK": Scenario(
        name="WAR_MIDEAST_OIL_SHOCK",
        summary="Middle East conflict broadens and drives a sustained crude/oil-risk premium.",
        beneficiaries=["Energy producers", "Defense", "Commodity exporters"],
        pressured=["Airlines", "Consumer discretionary", "Oil-importing economies"],
        key_tells=["Brent/WTI spike", "Insurance and shipping costs surge", "Strategic reserve commentary"],
    ),
    "REGULATORY_BIG_TECH_CRACKDOWN": Scenario(
        name="REGULATORY_BIG_TECH_CRACKDOWN",
        summary="Antitrust and AI regulation tighten platform economics and distribution power.",
        beneficiaries=["Niche challengers", "Compliance software", "Regional incumbents"],
        pressured=["Platform monopolies", "Ad-tech concentration models"],
        key_tells=["New fines/rulings", "Model licensing constraints", "Data localization mandates"],
    ),
    "DEGLOBALIZATION_TARIFFS": Scenario(
        name="DEGLOBALIZATION_TARIFFS",
        summary="Trade barriers and strategic tariffs rise, increasing supply-chain friction.",
        beneficiaries=["Domestic manufacturing", "Defense and logistics localization", "Automation"],
        pressured=["Global low-cost import models", "Margin-thin retailers"],
        key_tells=["Tariff announcements", "Reshoring incentives", "Supplier relocation capex"],
    ),
    "ENERGY_TRANSITION_ACCELERATION": Scenario(
        name="ENERGY_TRANSITION_ACCELERATION",
        summary="Grid modernization and clean-energy deployment accelerate via policy and economics.",
        beneficiaries=["Grid equipment", "Nuclear and storage", "Transmission infrastructure"],
        pressured=["Legacy high-emission assets", "Slow-transition industrial operators"],
        key_tells=["Utility capex upcycles", "Permitting improvements", "Stable subsidy visibility"],
    ),
    "RESHORING_INDUSTRIAL_BOOM": Scenario(
        name="RESHORING_INDUSTRIAL_BOOM",
        summary="Domestic onshoring and strategic manufacturing investment stay elevated for years.",
        beneficiaries=["Industrial automation", "Factory suppliers", "Domestic logistics"],
        pressured=["Offshore-dependent contract manufacturing"],
        key_tells=["Large fab/factory announcements", "Public-private incentives", "Capex order backlogs"],
    ),
    "DEMOGRAPHIC_AGING": Scenario(
        name="DEMOGRAPHIC_AGING",
        summary="Aging populations shift demand toward healthcare, retirement, and productivity tech.",
        beneficiaries=["Healthcare devices/services", "Retirement services", "Automation software"],
        pressured=["Youth-driven discretionary categories"],
        key_tells=["Healthcare spend share rising", "Labor shortages", "Policy focus on elder care"],
    ),
    "CRYPTO_RISK_ON": Scenario(
        name="CRYPTO_RISK_ON",
        summary="Digital-asset liquidity improves, lifting broader speculative risk appetite.",
        beneficiaries=["High-beta growth", "Trading platforms", "Select fintech"],
        pressured=["Pure defensives in momentum-led markets"],
        key_tells=["Rising crypto market cap", "ETF inflow acceleration", "Retail risk appetite broadening"],
    ),
}


SECTOR_SCENARIO_MAP: Dict[str, List[str]] = {
    "technology": ["AI_CAPEX_ACCELERATION", "AI_CAPEX_PULLBACK", "REGULATORY_BIG_TECH_CRACKDOWN", "RATE_CUT_CYCLE"],
    "semiconductors": ["AI_CAPEX_ACCELERATION", "AI_CAPEX_PULLBACK", "WAR_TAIWAN_ESCALATION", "DEGLOBALIZATION_TARIFFS"],
    "defense": ["WAR_TAIWAN_ESCALATION", "WAR_MIDEAST_OIL_SHOCK", "DEGLOBALIZATION_TARIFFS", "RESHORING_INDUSTRIAL_BOOM"],
    "energy": ["WAR_MIDEAST_OIL_SHOCK", "ENERGY_TRANSITION_ACCELERATION", "RECESSION_HARD_LANDING"],
    "industrials": ["RESHORING_INDUSTRIAL_BOOM", "DEGLOBALIZATION_TARIFFS", "RECESSION_HARD_LANDING"],
    "healthcare": ["DEMOGRAPHIC_AGING", "RECESSION_HARD_LANDING", "RATE_CUT_CYCLE"],
    "financials": ["RATE_CUT_CYCLE", "RECESSION_HARD_LANDING", "CRYPTO_RISK_ON"],
    "consumer discretionary": ["RECESSION_HARD_LANDING", "RATE_CUT_CYCLE", "WAR_MIDEAST_OIL_SHOCK"],
}


def _format_scenarios(keys: Iterable[str]) -> str:
    blocks = []
    for key in keys:
        scenario = SCENARIOS.get(key)
        if not scenario:
            continue
        blocks.append(
            "\n".join(
                [
                    f"### {scenario.name}",
                    f"- Summary: {scenario.summary}",
                    f"- Beneficiaries: {', '.join(scenario.beneficiaries)}",
                    f"- Pressured: {', '.join(scenario.pressured)}",
                    f"- Key tells: {', '.join(scenario.key_tells)}",
                ]
            )
        )
    return "\n\n".join(blocks)


def get_all_scenarios_text() -> str:
    """Return the full scenario playbook as prompt-ready markdown."""
    return _format_scenarios(SCENARIOS.keys())


def get_scenarios_for_sector(sector: str) -> str:
    """Return a sector-focused scenario subset with sensible fallbacks."""
    normalized = (sector or "").strip().lower()
    keys = SECTOR_SCENARIO_MAP.get(normalized)
    if not keys:
        # Fallback blend for unknown sectors.
        keys = [
            "AI_CAPEX_ACCELERATION",
            "AI_CAPEX_PULLBACK",
            "RATE_CUT_CYCLE",
            "RECESSION_HARD_LANDING",
            "WAR_MIDEAST_OIL_SHOCK",
        ]
    return _format_scenarios(keys)
