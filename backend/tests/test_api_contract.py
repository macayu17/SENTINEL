import asyncio
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.api import main as api_main
from backend.src.market.order import Order, OrderSide, OrderType


def test_live_shadow_routes_are_removed():
    paths = {route.path for route in api_main.app.routes}

    assert not any(path.startswith("/api/live-shadow") for path in paths)


def test_duplicate_simulation_routes_are_removed():
    paths = {route.path for route in api_main.app.routes}

    for path in (
        "/api/simulation/start",
        "/api/prediction/liquidity",
        "/api/prediction/large-order",
        "/api/agents/metrics",
        "/api/market/snapshot",
        "/api/sandbox/oracle",
    ):
        assert path not in paths


def test_playback_speed_uses_the_full_supported_range():
    assert api_main._clamp_simulation_speed(0.01) == 0.1
    assert api_main._clamp_simulation_speed(7.5) == 7.5
    assert api_main._clamp_simulation_speed(100) == 20.0
    assert 0.1 / api_main._clamp_simulation_speed(20) == pytest.approx(0.005)


def test_local_next_dev_ports_are_allowed_for_cors_preflight():
    client = TestClient(api_main.app)

    response = client.options(
        "/api/sandbox/create",
        headers={
            "Origin": "http://127.0.0.1:3002",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3002"


def test_sandbox_scenarios_endpoint_exposes_regimes():
    client = TestClient(api_main.app)

    response = client.get("/api/sandbox/scenarios")

    assert response.status_code == 200
    names = {scenario["name"] for scenario in response.json()["scenarios"]}
    assert "normal" in names
    assert "spoofing_stress" in names
    assert "liquidity_shock" in names


def test_sandbox_create_applies_selected_scenario():
    request = api_main.SandboxCreateRequest(
        preset="balanced",
        initial_price=100.0,
        oracle_enabled=False,
        latency_mode="deterministic",
        speed=10.0,
        scenario="spoofing_stress",
    )

    async def create_sandbox():
        response = await api_main.create_sandbox(request)
        if api_main._sim_task:
            api_main._sim_task.cancel()
            try:
                await api_main._sim_task
            except asyncio.CancelledError:
                pass
            api_main._sim_task = None
        return response

    try:
        response = asyncio.run(create_sandbox())
        assert response["scenario"] == "spoofing_stress"
        assert api_main.simulator is not None
        assert api_main.simulator.scenario.name == "spoofing_stress"
        assert any(agent.agent_type == "Spoofing" for agent in api_main.simulator.agents)
    finally:
        if api_main.simulator:
            api_main.simulator.stop()
        api_main.simulator = None
        api_main._sim_task = None


def test_sandbox_create_uses_requested_seed():
    request = api_main.SandboxCreateRequest(seed=1729)

    async def create_sandbox():
        response = await api_main.create_sandbox(request)
        if api_main._sim_task:
            api_main._sim_task.cancel()
            try:
                await api_main._sim_task
            except asyncio.CancelledError:
                pass
            api_main._sim_task = None
        return response

    try:
        response = asyncio.run(create_sandbox())

        assert response["seed"] == 1729
        assert api_main.simulator is not None
        assert api_main.simulator.seed == 1729
    finally:
        if api_main.simulator:
            api_main.simulator.stop()
        api_main.simulator = None
        api_main._sim_task = None


def test_sandbox_create_generates_seed_when_request_omits_it():
    request = api_main.SandboxCreateRequest()

    async def create_sandbox():
        response = await api_main.create_sandbox(request)
        if api_main._sim_task:
            api_main._sim_task.cancel()
            try:
                await api_main._sim_task
            except asyncio.CancelledError:
                pass
            api_main._sim_task = None
        return response

    try:
        response = asyncio.run(create_sandbox())

        assert isinstance(response["seed"], int)
    finally:
        if api_main.simulator:
            api_main.simulator.stop()
        api_main.simulator = None
        api_main._sim_task = None


def test_sandbox_defaults_to_calibrated_hidden_reference_process():
    request = api_main.SandboxCreateRequest(seed=101)

    async def create_sandbox():
        response = await api_main.create_sandbox(request)
        if api_main._sim_task:
            api_main._sim_task.cancel()
            try:
                await api_main._sim_task
            except asyncio.CancelledError:
                pass
            api_main._sim_task = None
        return response

    try:
        asyncio.run(create_sandbox())

        assert api_main.simulator is not None
        assert api_main.simulator.oracle.enabled is True
        assert api_main.simulator.informed_oracle_access is False
        assert api_main.simulator.oracle.config.kappa == pytest.approx(0.001)
        assert api_main.simulator.oracle.config.sigma_s == pytest.approx(
            100.0 * 0.30 / (252 * 390 * 60) ** 0.5
        )
        assert "oracle" not in api_main.simulator.get_market_state()
    finally:
        if api_main.simulator:
            api_main.simulator.stop()
        api_main.simulator = None
        api_main._sim_task = None


def test_market_update_includes_real_trace_contract_fields():
    active_sim = api_main.MarketSimulator([], initial_price=100.0)
    active_sim.order_book.replace_depth(
        bids=[{"price": 99.9, "size": 100}],
        asks=[{"price": 100.1, "size": 100}],
    )
    active_sim._process_order(
        Order(
            agent_id="TRACE_AGENT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            price=100.0,
            quantity=25,
        )
    )

    update = api_main._build_market_update(
        state=active_sim.get_market_state(),
        liquidity_prediction={"warning_level": "safe"},
        large_order_detection=None,
        agent_metrics={},
        active_simulator=active_sim,
    )

    assert "events" in update
    assert "order_flow" in update
    assert "recent_orders" in update
    assert any(event["type"] == "order_submission" for event in update["events"])
    assert any(event["type"] == "fill" for event in update["events"])
    assert update["order_flow"]["submitted"] == 1
    assert update["order_flow"]["fills"] == 1
    assert update["order_flow"]["buy_volume"] == 25
    assert update["recent_orders"][0]["status"] == "filled"
    assert update["session_phase"] == "OPEN"
    assert update["activity_multiplier"] == 1.5
    assert update["scenario"]["name"] == "normal"
    assert update["latency_mode"] == "DETERMINISTIC"


def test_simulation_export_returns_run_config_metrics_and_warning_timeline():
    active_sim = api_main.MarketSimulator([], initial_price=100.0, scenario="market_open")
    active_sim.running = True
    for _ in range(3):
        active_sim.step()
    api_main.simulator = active_sim
    api_main._warning_timeline = [
        {"timestamp": 1.0, "warning_level": "caution", "probability": 0.25}
    ]
    client = TestClient(api_main.app)

    try:
        response = client.get("/api/simulation/export")
        payload = response.json()

        assert response.status_code == 200
        assert payload["run_config"]["scenario"] == "market_open"
        assert "seed" in payload["run_config"]
        assert "detector_hits" not in payload
        assert payload["warning_timeline"][0]["warning_level"] == "caution"
        assert "spread_mean" in payload["validation_metrics"]
        assert "trade_rate_per_second_mean" in payload["validation_metrics"]
        assert "fill_rate_mean" not in payload["validation_metrics"]
        assert "cancel_to_trade_ratio" in payload["validation_metrics"]
        assert "slippage_bps_mean" in payload["validation_metrics"]
        assert len(payload["price_path"]) >= 3
    finally:
        active_sim.stop()
        api_main.simulator = None
        api_main._warning_timeline = []
