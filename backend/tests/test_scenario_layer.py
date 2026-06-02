from backend.src.market.scenario import (
    apply_scenario_agent_counts,
    get_scenario_config,
    list_scenarios,
)
from backend.src.market.simulator import MarketSimulator, get_sandbox_presets


def test_scenario_registry_exposes_required_regimes():
    names = {scenario["name"] for scenario in list_scenarios()}

    assert {
        "normal",
        "market_open",
        "liquidity_shock",
        "institutional_execution",
        "volatility_spike",
        "spoofing_stress",
        "close_auction",
    }.issubset(names)


def test_normal_preset_excludes_spoofing_until_stress_scenario_enables_it():
    balanced = get_sandbox_presets()["balanced"]["agents"]

    assert balanced.get("Spoofing", 0) == 0

    normal_counts = apply_scenario_agent_counts(balanced, "normal")
    stress_counts = apply_scenario_agent_counts(balanced, "spoofing_stress")

    assert normal_counts.get("Spoofing", 0) == 0
    assert stress_counts["Spoofing"] >= 1


def test_market_simulator_state_includes_scenario_and_uses_depth_profile():
    scenario = get_scenario_config("liquidity_shock")
    simulator = MarketSimulator([], initial_price=100.0, scenario=scenario.name)

    state = simulator.get_market_state()

    assert state["scenario"]["name"] == "liquidity_shock"
    assert state["scenario"]["label"] == scenario.label
    assert state["total_depth"] < MarketSimulator([], initial_price=100.0).get_market_state()["total_depth"]
