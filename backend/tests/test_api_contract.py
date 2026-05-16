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
