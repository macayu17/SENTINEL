import asyncio
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.api import main as api_main


def test_invalid_simulation_mode_returns_bad_request():
    client = TestClient(api_main.app)

    response = client.post("/api/simulation/mode", json={"mode": "INVALID"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid mode"


def test_market_data_endpoints_require_active_simulation():
    api_main.simulator = None
    client = TestClient(api_main.app)

    for path in [
        "/api/prediction/liquidity",
        "/api/prediction/large-order",
        "/api/agents/metrics",
        "/api/market/snapshot",
    ]:
        response = client.get(path)
        assert response.status_code == 409
        assert response.json()["detail"] == "No active simulation"


def test_abides_api_loop_initializes_agents_before_steps():
    if not api_main.ABIDES_AVAILABLE:
        pytest.skip("ABIDES module is not available")

    api_main.abides_simulator = api_main.AbidesSimulation(
        oracle_config=api_main.OracleConfig(enabled=False),
        speed_multiplier=10.0,
    )
    exchange = api_main.AbidesExchangeAgent(initial_price=100.0)
    api_main.abides_simulator.set_exchange(exchange)
    api_main.abides_simulator.register_agent(
        api_main.AbidesMarketMakerAgent("AB_MM_1", wakeup_interval=0.5)
    )
    api_main.abides_simulator.register_agent(
        api_main.AbidesNoiseAgent("AB_NOISE_1", wakeup_interval=0.4, order_rate=1.0)
    )

    async def run_short_loop():
        task = asyncio.create_task(api_main._run_abides_loop())
        await asyncio.sleep(0.15)
        api_main.abides_simulator.running = False
        await asyncio.wait_for(task, timeout=1.0)

    try:
        asyncio.run(run_short_loop())
        state = api_main.abides_simulator.get_state()
        assert state["total_depth"] > 0
        assert state["bid_levels"] or state["ask_levels"]
    finally:
        api_main.abides_simulator = None
        api_main._abides_task = None


def test_abides_create_enables_oracle_when_informed_agents_requested():
    if not api_main.ABIDES_AVAILABLE:
        pytest.skip("ABIDES module is not available")

    request = api_main.AbidesSandboxCreateRequest(
        initial_price=100.0,
        oracle_enabled=False,
        oracle_kappa=0.05,
        oracle_sigma=0.02,
        latency_mode="deterministic",
        speed=10.0,
        market_makers=1,
        noise_agents=1,
        informed_agents=2,
    )

    async def create_sandbox():
        response = await api_main.create_abides_sandbox(request)
        if api_main.abides_simulator:
            api_main.abides_simulator.running = False
        if api_main._abides_task:
            api_main._abides_task.cancel()
            try:
                await api_main._abides_task
            except asyncio.CancelledError:
                pass
            api_main._abides_task = None
        return response

    try:
        response = asyncio.run(create_sandbox())
        assert response["oracle_enabled"] is True
        assert response["oracle_auto_enabled"] is True
        assert api_main.abides_simulator is not None
        assert api_main.abides_simulator.oracle.enabled is True
    finally:
        if api_main.abides_simulator:
            api_main.abides_simulator.running = False
        api_main.abides_simulator = None
        api_main._abides_task = None
