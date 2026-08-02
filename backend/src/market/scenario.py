"""Scenario/regime definitions for SENTINEL sandbox runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    label: str
    description: str
    seed_depth_multiplier: float = 1.0
    liquidity_floor_multiplier: float = 1.0
    spread_multiplier: float = 1.0
    oracle_sigma_multiplier: float = 1.0
    order_ttl_seconds: float = 20.0
    volatility_multiplier: float = 1.0
    enable_spoofing: bool = False
    enable_opening_auction: bool = False
    institutional_multiplier: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


SCENARIOS: dict[str, ScenarioConfig] = {
    "normal": ScenarioConfig(
        name="normal",
        label="Normal Session",
        description="Balanced continuous double-auction session with non-adversarial agents.",
    ),
    "market_open": ScenarioConfig(
        name="market_open",
        label="Market Open",
        description="Pre-open order accumulation, a uniform-price uncrossing, then a wide, fast open.",
        seed_depth_multiplier=1.35,
        liquidity_floor_multiplier=1.25,
        spread_multiplier=2.5,
        order_ttl_seconds=8.0,
        volatility_multiplier=1.4,
        enable_opening_auction=True,
    ),
    "liquidity_shock": ScenarioConfig(
        name="liquidity_shock",
        label="Liquidity Shock",
        description="Normal book followed by quote withdrawal, aggressive flow, and measured recovery.",
    ),
    "institutional_execution": ScenarioConfig(
        name="institutional_execution",
        label="Institutional Execution",
        description="Elevated institutional parent-order activity and child-order flow.",
        seed_depth_multiplier=1.15,
        liquidity_floor_multiplier=1.0,
        spread_multiplier=1.25,
        institutional_multiplier=2.0,
        volatility_multiplier=1.2,
    ),
    "volatility_spike": ScenarioConfig(
        name="volatility_spike",
        label="Volatility Spike",
        description="Noisy high-volatility regime with wider quoting and smaller child orders.",
        seed_depth_multiplier=0.75,
        liquidity_floor_multiplier=0.8,
        spread_multiplier=3.0,
        oracle_sigma_multiplier=2.5,
        order_ttl_seconds=7.0,
        volatility_multiplier=2.8,
    ),
    "spoofing_stress": ScenarioConfig(
        name="spoofing_stress",
        label="Spoofing Stress",
        description="Adversarial stress run with quote-layering agents enabled.",
        seed_depth_multiplier=0.9,
        liquidity_floor_multiplier=0.8,
        spread_multiplier=1.75,
        order_ttl_seconds=6.0,
        volatility_multiplier=1.5,
        enable_spoofing=True,
    ),
    "close_auction": ScenarioConfig(
        name="close_auction",
        label="Close / Auction",
        description="Higher displayed depth and institutional activity near a synthetic close.",
        seed_depth_multiplier=1.8,
        liquidity_floor_multiplier=1.6,
        spread_multiplier=1.6,
        order_ttl_seconds=12.0,
        institutional_multiplier=1.4,
    ),
}


def get_scenario_config(name: str | None) -> ScenarioConfig:
    key = (name or "normal").strip().lower()
    return SCENARIOS.get(key, SCENARIOS["normal"])


def list_scenarios() -> list[dict]:
    return [scenario.to_dict() for scenario in SCENARIOS.values()]


def apply_scenario_agent_counts(
    counts: Mapping[str, int],
    scenario: str | ScenarioConfig | None,
) -> dict[str, int]:
    config = scenario if isinstance(scenario, ScenarioConfig) else get_scenario_config(scenario)
    adjusted = {key: max(0, int(value)) for key, value in counts.items()}

    if not config.enable_spoofing:
        adjusted["Spoofing"] = 0
    else:
        adjusted["Spoofing"] = max(1, adjusted.get("Spoofing", 0))

    if config.institutional_multiplier != 1.0:
        adjusted["Institutional"] = max(
            1,
            int(round(adjusted.get("Institutional", 0) * config.institutional_multiplier)),
        )

    return adjusted
