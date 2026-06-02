import asyncio
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.api import main as api_main
from backend.src.data import groww_provider, upstox_provider
from backend.src.data.groww_provider import GrowwQuote
from backend.src.data.upstox_provider import UpstoxCredentialsError, UpstoxInstrument, UpstoxQuote
from backend.src.market.order import Order, OrderSide, OrderType
from backend.src.market.market_data import StockInfo


def test_invalid_simulation_mode_returns_bad_request():
    client = TestClient(api_main.app)

    response = client.post("/api/simulation/mode", json={"mode": "INVALID"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid mode"


def test_generic_mode_endpoint_rejects_live_shadow_without_provider():
    api_main.simulator = None
    api_main.config.simulation_mode = "SANDBOX"
    client = TestClient(api_main.app)

    response = client.post("/api/simulation/mode", json={"mode": "LIVE_SHADOW"})

    assert response.status_code == 400
    assert "Live-shadow mode requires" in response.json()["detail"]
    assert api_main.config.simulation_mode == "SANDBOX"


def test_default_start_always_uses_sandbox_mode():
    api_main.simulator = None
    api_main.config.simulation_mode = "LIVE_SHADOW"

    async def start_default():
        response = await api_main.start_simulation()
        if api_main._sim_task:
            api_main._sim_task.cancel()
            try:
                await api_main._sim_task
            except asyncio.CancelledError:
                pass
            api_main._sim_task = None
        return response

    try:
        response = asyncio.run(start_default())
        assert response["status"] == "started"
        assert api_main.simulator is not None
        assert api_main.simulator.mode == "SANDBOX"
        assert api_main.config.simulation_mode == "SANDBOX"
    finally:
        if api_main.simulator:
            api_main.simulator.stop()
        api_main.simulator = None
        api_main._sim_task = None
        api_main.config.simulation_mode = "SANDBOX"


def test_stock_replay_always_uses_sandbox_mode(monkeypatch):
    sample = StockInfo(
        ticker="AAPL",
        name="Apple Inc.",
        currency="USD",
        last_close=103.0,
        period_start="2025-01-01T09:30:00",
        period_end="2025-01-01T10:30:00",
        bars=3,
        prices=[100.0, 101.0, 103.0],
        volumes=[1000, 1100, 1200],
        highs=[101.0, 102.0, 104.0],
        lows=[99.0, 100.5, 102.0],
        returns=[0.01, 0.0198],
        realized_vol=0.2,
        mean_return=0.0149,
    )

    monkeypatch.setattr(api_main, "fetch_stock", lambda **kwargs: sample)
    api_main.simulator = None
    api_main.config.simulation_mode = "LIVE_SHADOW"
    request = api_main.StockReplayRequest(ticker="AAPL", period="1d", interval="30m")

    async def start_replay():
        response = await api_main.start_stock_replay(request)
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
        assert api_main.simulator is not None
        assert api_main.simulator.mode == "SANDBOX"
        assert api_main.config.simulation_mode == "SANDBOX"
    finally:
        if api_main.simulator:
            api_main.simulator.stop()
        api_main.simulator = None
        api_main._sim_task = None
        api_main.config.simulation_mode = "SANDBOX"


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
        oracle_kappa=0.05,
        oracle_sigma=0.02,
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
        assert response["depth_source"] == "modeled_from_ohlcv"
        assert response["order_book_history"] == "unavailable_from_provider"
        assert api_main.simulator.data_source["depth_source"] == "modeled_from_ohlcv"
        assert api_main.simulator.data_source["order_book_history"] == "unavailable_from_provider"
        assert api_main.simulator.depth_profile["source"] == "ohlcv"
        assert "historical L2" in api_main.simulator.depth_profile["method"]
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
        assert response["depth_source"] == "modeled_from_ohlcv"
        assert response["order_book_history"] == "unavailable_from_provider"
        assert api_main.simulator.data_source["depth_source"] == "modeled_from_ohlcv"
        assert api_main.simulator.data_source["order_book_history"] == "unavailable_from_provider"
        assert api_main.simulator.depth_profile["source"] == "ohlcv"
    finally:
        if api_main.simulator:
            api_main.simulator.stop()
        api_main.simulator = None
        api_main._sim_task = None


def test_groww_fetch_missing_token_returns_clear_error(monkeypatch):
    monkeypatch.delenv("GROWW_API_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("GROWW_API_KEY", raising=False)
    monkeypatch.delenv("GROWW_API_SECRET", raising=False)
    monkeypatch.setattr(groww_provider, "_reload_environment_values", lambda names: None)
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
    monkeypatch.setattr(upstox_provider, "_reload_environment_values", lambda names: None)
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


def test_upstox_live_depth_starts_after_successful_provider_fetch(monkeypatch):
    quotes = [
        UpstoxQuote(
            instrument_key="NSE_EQ|INE002A01018",
            last_price=2510.0,
            ltq=5,
            volume=1000,
            previous_close=2500.0,
            depth_source="provider_live",
            order_book={
                "bids": [{"price": 2509.95, "size": 300}],
                "asks": [{"price": 2510.05, "size": 400}],
            },
        ),
        UpstoxQuote(
            instrument_key="NSE_EQ|INE002A01018",
            last_price=2522.5,
            ltq=8,
            volume=1500,
            previous_close=2500.0,
            depth_source="provider_live",
            order_book={
                "bids": [{"price": 2522.45, "size": 500}],
                "asks": [{"price": 2522.55, "size": 600}],
            },
        ),
    ]

    def fake_full_quote(**kwargs):
        assert kwargs["instrument_key"] == "NSE_EQ|INE002A01018"
        return quotes.pop(0)

    monkeypatch.setattr(api_main, "fetch_upstox_full_quote", fake_full_quote)
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
        assert response.json()["source"] == "live_depth"
        assert response.json()["initial_price"] == 2510.0
        assert response.json()["depth_source"] == "provider_live"
        assert api_main.simulator is not None
        assert api_main.simulator.mode == "LIVE_SHADOW"
        assert api_main.simulator.data_source["provider"] == "upstox"
        assert api_main.simulator.data_source["source"] == "live_depth"

        state = api_main.simulator.step()
        assert state["current_price"] == 2522.5
        assert state["bid_levels"] == [{"price": 2522.45, "size": 500}]
        assert state["ask_levels"] == [{"price": 2522.55, "size": 600}]
        assert api_main.simulator.data_source["last_price"] == 2522.5
        assert api_main.simulator.data_source["volume"] == 1500
    finally:
        if api_main.simulator:
            api_main.simulator.stop()
        if api_main._sim_task:
            api_main._sim_task.cancel()
        api_main.simulator = None
        api_main._sim_task = None


def test_upstox_live_depth_failure_does_not_freeze_existing_simulation(monkeypatch):
    old_simulator = api_main.MarketSimulator([], initial_price=100.0, mode="SANDBOX")
    old_simulator.running = True
    api_main.simulator = old_simulator

    def fake_full_quote(**kwargs):
        raise UpstoxCredentialsError("Upstox rejected quote access")

    monkeypatch.setattr(api_main, "fetch_upstox_full_quote", fake_full_quote)
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


def test_groww_live_depth_starts_after_successful_provider_fetch(monkeypatch):
    quotes = [
        GrowwQuote(
            groww_symbol="NSE-RELIANCE",
            exchange="NSE",
            segment="CASH",
            last_price=149.5,
            ltq=20,
            volume=10000,
            previous_close=148.5,
            depth_source="provider_live",
            order_book={
                "bids": [{"price": 149.45, "size": 1000}],
                "asks": [{"price": 149.55, "size": 900}],
            },
        ),
        GrowwQuote(
            groww_symbol="NSE-RELIANCE",
            exchange="NSE",
            segment="CASH",
            last_price=150.25,
            ltq=25,
            volume=12000,
            previous_close=148.5,
            depth_source="provider_live",
            order_book={
                "bids": [{"price": 150.2, "size": 1100}],
                "asks": [{"price": 150.3, "size": 950}],
            },
        ),
    ]

    def fake_quote(**kwargs):
        assert kwargs["groww_symbol"] == "NSE-RELIANCE"
        assert kwargs["segment"] == "CASH"
        return quotes.pop(0)

    monkeypatch.setattr(api_main, "fetch_groww_quote", fake_quote)
    client = TestClient(api_main.app)

    response = client.post(
        "/api/live-shadow/groww/live",
        json={
            "groww_symbol": "RELIANCE",
            "exchange": "NSE",
            "segment": "CASH",
            "speed": 2.0,
            "poll_interval_seconds": 1,
        },
    )

    try:
        assert response.status_code == 200
        assert response.json()["source"] == "live_depth"
        assert response.json()["initial_price"] == 149.5
        assert response.json()["depth_source"] == "provider_live"
        assert api_main.simulator is not None
        assert api_main.simulator.mode == "LIVE_SHADOW"
        assert api_main.simulator.data_source["provider"] == "groww"
        assert api_main.simulator.data_source["source"] == "live_depth"

        state = api_main.simulator.step()
        assert state["current_price"] == 150.25
        assert state["bid_levels"] == [{"price": 150.2, "size": 1100}]
        assert state["ask_levels"] == [{"price": 150.3, "size": 950}]
        assert api_main.simulator.data_source["last_price"] == 150.25
    finally:
        if api_main.simulator:
            api_main.simulator.stop()
        if api_main._sim_task:
            api_main._sim_task.cancel()
        api_main.simulator = None
        api_main._sim_task = None


def test_groww_live_depth_marks_modeled_fallback_when_provider_has_no_depth(monkeypatch):
    quote = GrowwQuote(
        groww_symbol="NSE-RELIANCE",
        exchange="NSE",
        segment="CASH",
        last_price=149.5,
        ltq=20,
        volume=10000,
        previous_close=148.5,
        depth_source=None,
        order_book=None,
    )

    monkeypatch.setattr(api_main, "fetch_groww_quote", lambda **kwargs: quote)
    client = TestClient(api_main.app)

    response = client.post(
        "/api/live-shadow/groww/live",
        json={
            "groww_symbol": "RELIANCE",
            "exchange": "NSE",
            "segment": "CASH",
            "speed": 2.0,
            "poll_interval_seconds": 1,
        },
    )

    try:
        assert response.status_code == 200
        assert response.json()["depth_source"] == "modeled_live_fallback"
        assert api_main.simulator is not None
        assert api_main.simulator.data_source["depth_source"] == "modeled_live_fallback"
    finally:
        if api_main.simulator:
            api_main.simulator.stop()
        if api_main._sim_task:
            api_main._sim_task.cancel()
        api_main.simulator = None
        api_main._sim_task = None


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


def test_market_update_includes_real_trace_contract_fields():
    active_sim = api_main.MarketSimulator([], initial_price=100.0, mode="SANDBOX")
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


def test_health_reports_abides_as_active_engine_when_abides_running():
    exchange = api_main.AbidesExchangeAgent(initial_price=100.0)
    abides = api_main.AbidesSimulation()
    abides.set_exchange(exchange)
    abides.running = True
    abides.step_count = 7
    api_main.simulator = None
    api_main.abides_simulator = abides

    try:
        payload = asyncio.run(api_main.health_check())

        assert payload["simulation_active"] is True
        assert payload["engine"] == "ABIDES"
        assert payload["abides"]["running"] is True
        assert payload["abides"]["step"] == 7
    finally:
        api_main.abides_simulator = None


def test_export_returns_abides_snapshot_when_abides_is_active():
    exchange = api_main.AbidesExchangeAgent(initial_price=100.0)
    abides = api_main.AbidesSimulation(speed_multiplier=2.0)
    abides.set_exchange(exchange)
    abides.running = True
    abides.step_count = 3
    api_main.simulator = None
    api_main.abides_simulator = abides
    client = TestClient(api_main.app)

    try:
        response = client.get("/api/simulation/export")
        payload = response.json()

        assert response.status_code == 200
        assert payload["run_config"]["engine"] == "ABIDES"
        assert payload["run_config"]["speed"] == 2.0
        assert "agent_metrics" in payload
        assert "order_flow" in payload
    finally:
        abides.running = False
        api_main.abides_simulator = None


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
        assert "detector_hits" in payload
        assert payload["warning_timeline"][0]["warning_level"] == "caution"
        assert "spread_mean" in payload["validation_metrics"]
        assert "cancel_to_trade_ratio" in payload["validation_metrics"]
        assert "slippage_bps_mean" in payload["validation_metrics"]
        assert len(payload["price_path"]) >= 3
    finally:
        active_sim.stop()
        api_main.simulator = None
        api_main._warning_timeline = []
