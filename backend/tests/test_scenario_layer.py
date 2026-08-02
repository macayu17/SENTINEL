from backend.src.market.scenario import (
    apply_scenario_agent_counts,
    get_scenario_config,
    list_scenarios,
)
from backend.src.market.oracle import OracleConfig
from backend.src.market.order import Order, OrderSide, OrderType
from backend.src.market.simulator import MarketSimulator, create_sandbox_agents, get_sandbox_presets


def _agent_population_profile(agents):
    return [
        (
            agent.agent_type,
            agent.latency_seconds,
            getattr(agent, "wakeup_interval", 1.0),
            agent.risk_profile.max_inventory,
            agent.risk_profile.base_order_size,
        )
        for agent in agents
    ]


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


def test_balanced_preset_matches_forty_agent_label_with_liquidity_flow():
    balanced = get_sandbox_presets()["balanced"]["agents"]

    assert sum(balanced.values()) == 40
    assert balanced["LiquidityTrader"] == 1


def test_sandbox_agent_factory_supports_every_preset_agent_type():
    for preset_name, preset in get_sandbox_presets().items():
        requested = {name: 1 for name in preset["agents"]}
        agents = create_sandbox_agents(preset_name, custom_agents=requested, scenario="spoofing_stress")

        created_types = {agent.agent_type for agent in agents}
        assert set(requested).issubset(created_types)


def test_sandbox_agent_population_is_reproducible_for_same_seed():
    first = create_sandbox_agents("balanced", seed=8128)
    second = create_sandbox_agents("balanced", seed=8128)

    assert _agent_population_profile(first) == _agent_population_profile(second)


def test_sandbox_agent_population_varies_without_changing_mix():
    first = create_sandbox_agents("balanced", seed=8128)
    second = create_sandbox_agents("balanced", seed=8129)

    assert [agent.agent_type for agent in first] == [agent.agent_type for agent in second]
    assert _agent_population_profile(first) != _agent_population_profile(second)

    noise_profiles = [
        profile for profile in _agent_population_profile(first) if profile[0] == "Noise"
    ]
    assert len(set(noise_profiles)) > 1


def test_liquidity_shock_starts_from_normal_liquidity_and_agent_population():
    scenario = get_scenario_config("liquidity_shock")
    normal = MarketSimulator([], initial_price=100.0, scenario="normal")
    stressed = MarketSimulator([], initial_price=100.0, scenario=scenario.name)
    normal_agents = create_sandbox_agents("balanced", scenario="normal", seed=7)
    stressed_agents = create_sandbox_agents("balanced", scenario=scenario.name, seed=7)

    state = stressed.get_market_state()

    assert state["scenario"]["name"] == "liquidity_shock"
    assert state["scenario"]["label"] == scenario.label
    assert state["scenario"]["phase"] == "WARMUP"
    assert state["total_depth"] == normal.get_market_state()["total_depth"]
    assert state["spread"] == normal.get_market_state()["spread"]
    assert [agent.agent_type for agent in stressed_agents] == [
        agent.agent_type for agent in normal_agents
    ]


def test_liquidity_shock_withdraws_executes_and_recovers_through_the_book():
    simulator = MarketSimulator(
        [],
        initial_price=100.0,
        duration_seconds=100,
        scenario="liquidity_shock",
        oracle_config=OracleConfig(enabled=False),
        seed=17,
    )
    simulator.running = True
    initial = simulator.get_market_state()

    for _ in range(34):
        state = simulator.step()

    assert state["scenario"]["phase"] == "WARMUP"
    assert not {
        event["type"] for event in simulator.get_recent_events(limit=500)
    }.intersection({"liquidity_withdrawal", "liquidity_impact"})

    impact = simulator.step()
    event_types = {
        event["type"] for event in simulator.get_recent_events(limit=500)
    }
    shock_trades = [
        trade for trade in simulator._all_trades
        if trade.taker_agent_id == "LIQUIDITY_SHOCK_FLOW"
    ]

    assert impact["scenario"]["phase"] == "IMPACT"
    assert {"liquidity_withdrawal", "liquidity_impact"}.issubset(event_types)
    assert impact["total_depth"] < initial["total_depth"] * 0.6
    assert impact["spread"] > initial["spread"]
    assert simulator._accepted_cancel_count > 0
    assert shock_trades

    for _ in range(20):
        recovered = simulator.step()

    assert recovered["scenario"]["phase"] == "NORMALIZED"
    assert recovered["scenario"]["liquidity"]["recovery_progress"] == 1.0
    assert recovered["total_depth"] > impact["total_depth"]
    assert recovered["spread"] < impact["spread"]


def test_liquidity_shock_uses_the_live_preimpact_book_as_its_baseline():
    simulator = MarketSimulator(
        [],
        duration_seconds=100,
        scenario="liquidity_shock",
        oracle_config=OracleConfig(enabled=False),
        seed=23,
    )
    simulator.running = True
    for _ in range(34):
        simulator.step()
    simulator.order_book.add_order(
        Order("warmup_bid", OrderSide.BUY, OrderType.LIMIT, 99.98, 4_000)
    )
    simulator.order_book.add_order(
        Order("warmup_ask", OrderSide.SELL, OrderType.LIMIT, 100.02, 4_000)
    )
    preimpact_depth = simulator.order_book.get_total_depth(levels=10)

    impact = simulator.step()

    assert impact["scenario"]["liquidity"]["baseline_depth"] == preimpact_depth


def test_liquidity_shock_refills_most_preimpact_depth_within_twenty_updates():
    simulator = MarketSimulator(
        create_sandbox_agents("balanced", scenario="liquidity_shock", seed=9),
        duration_seconds=300,
        scenario="liquidity_shock",
        oracle_config=OracleConfig(enabled=False),
        seed=9,
    )
    simulator.running = True
    for _ in range(60):
        impact = simulator.step()
    baseline_depth = impact["scenario"]["liquidity"]["baseline_depth"]
    for _ in range(20):
        recovered = simulator.step()

    assert recovered["total_depth"] >= baseline_depth * 0.7


def test_sandbox_session_profile_tracks_intraday_activity_curve():
    simulator = MarketSimulator([], duration_seconds=100)

    simulator.kernel.current_time = 5
    assert simulator._session_profile() == ("OPEN", 1.5)

    simulator.kernel.current_time = 50
    assert simulator._session_profile() == ("CONTINUOUS", 0.85)

    simulator.kernel.current_time = 95
    assert simulator._session_profile() == ("CLOSE", 1.35)
    state = simulator.get_market_state()
    assert state["session_phase"] == "CLOSE"
    assert state["activity_multiplier"] == 1.35


def test_seeded_simulator_reset_reproduces_initial_wakeup_schedule():
    agents = create_sandbox_agents(
        custom_agents={"Noise": 3},
        seed=2026,
    )
    simulator = MarketSimulator(agents, duration_seconds=100, seed=99)
    first_schedule = [
        (event.timestamp, event.data.agent_id)
        for event in sorted(simulator.kernel.queue)
    ]

    simulator.reset()
    second_schedule = [
        (event.timestamp, event.data.agent_id)
        for event in sorted(simulator.kernel.queue)
    ]

    assert first_schedule == second_schedule


def test_volatility_spike_has_an_explicit_two_sided_flow_driver():
    normal = MarketSimulator([], scenario="normal", duration_seconds=300, seed=77)
    stressed = MarketSimulator([], scenario="volatility_spike", duration_seconds=300, seed=77)
    normal.running = True
    stressed.running = True

    normal_prices = [normal.step()["current_price"] for _ in range(125)]
    stressed_prices = [stressed.step()["current_price"] for _ in range(125)]
    driver_events = [
        event for event in stressed.get_recent_events(limit=500)
        if event["type"] == "scenario_driver"
    ]

    assert {event["side"] for event in driver_events} == {"BUY", "SELL"}
    assert max(stressed_prices) - min(stressed_prices) > max(normal_prices) - min(normal_prices)
