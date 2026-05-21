import asyncio
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.api import main as api_main
from backend.src.data.upstox_provider import UpstoxCredentialsError, UpstoxInstrument, UpstoxQuote
from backend.src.market.market_data import StockInfo


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


def test_local_next_dev_ports_are_allowed_for_cors_preflight():
    client = TestClient(api_main.app)

    response = client.options(
        "/api/simulation/mode",
        headers={
            "Origin": "http://127.0.0.1:3002",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3002"


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


def test_groww_live_shadow_replay_starts_oracle_path(monkeypatch):
    sample = StockInfo(
        ticker="NSE-WIPRO",
        name="NSE-WIPRO Groww CASH",
        currency="INR",
        last_close=246.5,
        period_start="2025-09-24T10:30:00",
        period_end="2025-09-24T11:00:00",
        bars=3,
        prices=[245.6, 246.1, 246.5],
        volumes=[1000, 1200, 1300],
        highs=[246.0, 246.3, 246.8],
        lows=[245.1, 245.8, 246.0],
        returns=[0.002, 0.0016],
        realized_vol=0.12,
        mean_return=0.0018,
    )

    def fake_fetch(**kwargs):
        assert kwargs["groww_symbol"] == "NSE-WIPRO"
        assert kwargs["segment"] == "CASH"
        return sample

    monkeypatch.setattr(api_main, "fetch_groww_historical_stock", fake_fetch)
    request = api_main.GrowwReplayRequest(
        groww_symbol="NSE-WIPRO",
        exchange="NSE",
        segment="CASH",
        start_time="2025-09-24 10:30:00",
        end_time="2025-09-24 11:00:00",
        candle_interval="MIN_30",
        speed=10.0,
    )

    async def start_replay():
        response = await api_main.start_groww_replay(request)
        if api_main._sim_task:
            api_main._sim_task.cancel()
            try:
                await api_main._sim_task
            except asyncio.CancelledError:
                pass
            api_main._sim_task = None
        return response

    try:
        response = asyncio.run(start_replay())
        assert response["status"] == "started"
        assert response["mode"] == "LIVE_SHADOW"
        assert response["provider"] == "groww"
        assert api_main.simulator is not None
        assert api_main.simulator.mode == "LIVE_SHADOW"
        assert api_main.simulator.oracle.enabled is True
        assert api_main.simulator.oracle.config.replay_path[:3] == sample.prices
        assert api_main.simulator.data_source["provider"] == "groww"
    finally:
        if api_main.simulator:
            api_main.simulator.stop()
        api_main.simulator = None
        api_main._sim_task = None


def test_upstox_live_shadow_replay_starts_oracle_path(monkeypatch):
    sample = StockInfo(
        ticker="NSE_EQ|INE002A01018",
        name="NSE_EQ|INE002A01018 Upstox minutes/30",
        currency="INR",
        last_close=2521.5,
        period_start="2025-01-01T09:15:00+05:30",
        period_end="2025-01-01T10:15:00+05:30",
        bars=3,
        prices=[2510.0, 2518.0, 2521.5],
        volumes=[1000, 1200, 1300],
        highs=[2512.0, 2520.0, 2524.0],
        lows=[2508.0, 2515.0, 2519.0],
        returns=[0.003, 0.0014],
        realized_vol=0.18,
        mean_return=0.0022,
    )

    def fake_fetch(**kwargs):
        assert kwargs["instrument_key"] == "NSE_EQ|INE002A01018"
        assert kwargs["unit"] == "minutes"
        assert kwargs["interval"] == "30"
        return sample

    monkeypatch.setattr(api_main, "fetch_upstox_historical_stock", fake_fetch)
    request = api_main.UpstoxReplayRequest(
        instrument_key="NSE_EQ|INE002A01018",
        unit="minutes",
        interval="30",
        from_date="2025-01-01",
        to_date="2025-01-01",
        speed=10.0,
    )

    async def start_replay():
        response = await api_main.start_upstox_replay(request)
        if api_main._sim_task:
            api_main._sim_task.cancel()
            try:
                await api_main._sim_task
            except asyncio.CancelledError:
                pass
            api_main._sim_task = None
        return response

    try:
        response = asyncio.run(start_replay())
        assert response["status"] == "started"
        assert response["mode"] == "LIVE_SHADOW"
        assert response["provider"] == "upstox"
        assert api_main.simulator is not None
        assert api_main.simulator.mode == "LIVE_SHADOW"
        assert api_main.simulator.oracle.enabled is True
        assert api_main.simulator.oracle.config.replay_path[:3] == sample.prices
        assert api_main.simulator.data_source["provider"] == "upstox"
        assert api_main.simulator.data_source["instrument_key"] == sample.ticker
    finally:
        if api_main.simulator:
            api_main.simulator.stop()
        api_main.simulator = None
        api_main._sim_task = None


def test_groww_fetch_missing_token_returns_clear_error(monkeypatch):
    monkeypatch.delenv("GROWW_API_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("GROWW_API_KEY", raising=False)
    monkeypatch.delenv("GROWW_API_SECRET", raising=False)
    client = TestClient(api_main.app)

    response = client.post(
        "/api/live-shadow/groww/fetch",
        json={
            "groww_symbol": "NSE-WIPRO",
            "exchange": "NSE",
            "segment": "CASH",
            "start_time": "2025-09-24 10:30:00",
            "end_time": "2025-09-24 11:00:00",
            "candle_interval": "MIN_30",
        },
    )

    assert response.status_code == 503
    assert "GROWW_API_AUTH_TOKEN" in response.json()["detail"]


def test_upstox_fetch_missing_token_returns_clear_error(monkeypatch):
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("UPSTOX_ANALYTICS_TOKEN", raising=False)
    client = TestClient(api_main.app)

    response = client.post(
        "/api/live-shadow/upstox/fetch",
        json={
            "instrument_key": "NSE_EQ|INE002A01018",
            "unit": "minutes",
            "interval": "30",
            "from_date": "2025-01-01",
            "to_date": "2025-01-01",
        },
    )

    assert response.status_code == 503
    assert "UPSTOX_ACCESS_TOKEN" in response.json()["detail"]


def test_upstox_instrument_search_endpoint_returns_matches(monkeypatch):
    def fake_search(**kwargs):
        assert kwargs["query"] == "Reliance"
        assert kwargs["exchanges"] == "NSE"
        assert kwargs["segments"] == "EQ"
        assert kwargs["records"] == 5
        return [
            UpstoxInstrument(
                instrument_key="NSE_EQ|INE002A01018",
                trading_symbol="RELIANCE",
                name="RELIANCE INDUSTRIES LTD",
                exchange="NSE",
                segment="NSE_EQ",
                instrument_type="EQ",
                isin="INE002A01018",
                short_name="Reliance",
            )
        ]

    monkeypatch.setattr(api_main, "search_upstox_instruments", fake_search)
    client = TestClient(api_main.app)

    response = client.get(
        "/api/live-shadow/upstox/instruments",
        params={"query": "Reliance", "exchanges": "NSE", "segments": "EQ", "records": 5},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["instrument_key"] == "NSE_EQ|INE002A01018"
    assert response.json()["results"][0]["trading_symbol"] == "RELIANCE"


def test_upstox_live_ltp_starts_after_successful_provider_fetch(monkeypatch):
    quotes = [
        UpstoxQuote(
            instrument_key="NSE_EQ|INE002A01018",
            last_price=2510.0,
            ltq=5,
            volume=1000,
            previous_close=2500.0,
        ),
        UpstoxQuote(
            instrument_key="NSE_EQ|INE002A01018",
            last_price=2522.5,
            ltq=8,
            volume=1500,
            previous_close=2500.0,
        ),
    ]

    def fake_ltp(**kwargs):
        assert kwargs["instrument_key"] == "NSE_EQ|INE002A01018"
        return quotes.pop(0)

    monkeypatch.setattr(api_main, "fetch_upstox_ltp_quote", fake_ltp)
    client = TestClient(api_main.app)

    response = client.post(
        "/api/live-shadow/upstox/live",
        json={
            "instrument_key": "NSE_EQ|INE002A01018",
            "preset": "balanced",
            "latency_mode": "deterministic",
            "speed": 2.0,
            "poll_interval_seconds": 1,
        },
    )

    try:
        assert response.status_code == 200
        assert response.json()["source"] == "live_ltp"
        assert response.json()["initial_price"] == 2510.0
        assert api_main.simulator is not None
        assert api_main.simulator.mode == "LIVE_SHADOW"
        assert api_main.simulator.data_source["provider"] == "upstox"
        assert api_main.simulator.data_source["source"] == "live_ltp"

        state = api_main.simulator.step()
        assert state["current_price"] == 2522.5
        assert api_main.simulator.data_source["last_price"] == 2522.5
        assert api_main.simulator.data_source["volume"] == 1500
    finally:
        if api_main.simulator:
            api_main.simulator.stop()
        if api_main._sim_task:
            api_main._sim_task.cancel()
        api_main.simulator = None
        api_main._sim_task = None


def test_upstox_live_ltp_failure_does_not_freeze_existing_simulation(monkeypatch):
    old_simulator = api_main.MarketSimulator([], initial_price=100.0, mode="SANDBOX")
    old_simulator.running = True
    api_main.simulator = old_simulator

    def fake_ltp(**kwargs):
        raise UpstoxCredentialsError("Upstox rejected quote access")

    monkeypatch.setattr(api_main, "fetch_upstox_ltp_quote", fake_ltp)
    client = TestClient(api_main.app)

    response = client.post(
        "/api/live-shadow/upstox/live",
        json={
            "instrument_key": "NSE_EQ|INE002A01018",
            "speed": 1.0,
            "poll_interval_seconds": 1,
        },
    )

    assert response.status_code == 503
    assert api_main.simulator is old_simulator
    assert api_main.simulator.running is True
    assert api_main.simulator.mode == "SANDBOX"

    api_main.simulator = None


def test_live_shadow_market_update_preserves_contract_with_groww_metadata():
    sample = StockInfo(
        ticker="NSE-WIPRO",
        name="NSE-WIPRO Groww CASH",
        currency="INR",
        last_close=246.5,
        period_start="2025-09-24T10:30:00",
        period_end="2025-09-24T11:00:00",
        bars=3,
        prices=[245.6, 246.1, 246.5],
        volumes=[1000, 1200, 1300],
        highs=[246.0, 246.3, 246.8],
        lows=[245.1, 245.8, 246.0],
        returns=[0.002, 0.0016],
        realized_vol=0.12,
        mean_return=0.0018,
    )
    oracle_cfg = api_main.OracleConfig(
        r_bar=sample.prices[0],
        sigma_s=0.001,
        enabled=True,
        replay_path=sample.prices,
    )
    active_sim = api_main.MarketSimulator(
        [],
        initial_price=sample.prices[0],
        mode="LIVE_SHADOW",
        oracle_config=oracle_cfg,
    )
    active_sim.data_source = {
        "provider": "groww",
        "source": "historical_replay",
        "status": "connected",
        "groww_symbol": sample.ticker,
    }
    active_sim.running = True

    state = active_sim.step()
    update = api_main._build_market_update(
        state=state,
        liquidity_prediction={"warning_level": "safe"},
        large_order_detection=None,
        agent_metrics={},
        active_simulator=active_sim,
    )

    for key in [
        "type",
        "timestamp",
        "price",
        "spread",
        "depth",
        "order_book",
        "liquidity_prediction",
        "large_order_detection",
        "agent_metrics",
        "step",
        "volatility",
        "mode",
        "speed",
    ]:
        assert key in update

    assert update["type"] == "market_update"
    assert update["mode"] == "LIVE_SHADOW"
    assert update["price"] == sample.prices[0]
    assert update["data_source"]["provider"] == "groww"
    assert update["data_source"]["source"] == "historical_replay"
