"""FastAPI application — REST endpoints and WebSocket for SENTINEL."""

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Optional
import asyncio

from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .websocket import ConnectionManager
from ..market.simulator import MarketSimulator, get_sandbox_presets, create_sandbox_agents
from ..market.oracle import OracleConfig
from ..market.latency_model import LatencyConfig, LatencyMode
from ..market.market_data import fetch_stock, build_oracle_path, POPULAR_TICKERS
from ..market.scenario import get_scenario_config, list_scenarios
from ..data.groww_provider import (
    GrowwProviderError,
    GrowwCredentialsError,
    GrowwSdkMissingError,
    fetch_groww_historical_stock,
    fetch_groww_quote,
    normalize_groww_symbol,
)
from ..data.upstox_provider import (
    UpstoxProviderError,
    UpstoxCredentialsError,
    fetch_upstox_full_quote,
    fetch_upstox_ltp_quote,
    fetch_upstox_historical_stock,
    normalize_upstox_instrument_key,
    search_upstox_instruments,
)
from ..agents.market_maker import MarketMakerAgent
from ..agents.hft_agent import HFTAgent
from ..agents.institutional import InstitutionalAgent
from ..agents.retail import RetailAgent
from ..agents.informed import InformedAgent
from ..agents.noise import NoiseAgent
from ..agents.momentum import MomentumAgent
from ..agents.mean_reversion import MeanReversionAgent
from ..agents.spoofing import SpoofingAgent
from ..agents.sentiment import SentimentAgent
from ..agents.rl_agent import RLAgent
from ..prediction.liquidity_shock import LiquidityShockPredictor
from ..prediction.large_order import LargeOrderDetector
from ..market.rl_policy import RLPolicyController
from ..utils.logger import get_logger
from ..utils.config import config

try:
    from ..abides.simulation import AbidesSimulation
    from ..abides.agents.exchange import ExchangeAgent as AbidesExchangeAgent
    from ..abides.agents.market_maker import MarketMakerAgent as AbidesMarketMakerAgent
    from ..abides.agents.noise import NoiseAgent as AbidesNoiseAgent
    from ..abides.agents.informed import InformedAgent as AbidesInformedAgent
    ABIDES_AVAILABLE = True
except Exception:
    AbidesSimulation = None
    AbidesExchangeAgent = None
    AbidesMarketMakerAgent = None
    AbidesNoiseAgent = None
    AbidesInformedAgent = None
    ABIDES_AVAILABLE = False

logger = get_logger("api")

# Global singletons
simulator: Optional[MarketSimulator] = None
abides_simulator: Optional["AbidesSimulation"] = None
liquidity_predictor = LiquidityShockPredictor()
large_order_detector = LargeOrderDetector()
rl_policy = (
    RLPolicyController(
        model_path=config.rl_model_path,
        policy_kind=config.rl_policy_kind,
        autoload=False,
    )
    if config.rl_policy_enabled
    else None
)
manager = ConnectionManager()

# Simulation task handle
_sim_task: Optional[asyncio.Task] = None
_abides_task: Optional[asyncio.Task] = None
_warning_timeline: list[dict] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SENTINEL API starting up")
    yield
    logger.info("SENTINEL API shutting down")


app = FastAPI(
    title="SENTINEL API",
    description="Smart Early-warning Network for Trading, Institutional orders, and Liquidity Events",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST Endpoints ──────────────────────────────────────────────────────────


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "simulation_active": simulator is not None and simulator.running,
        "connected_clients": manager.client_count,
        "mode": simulator.mode if simulator else config.simulation_mode,
        "rl_policy_ready": rl_policy.ready if rl_policy else False,
        "rl_policy_kind": rl_policy.loaded_policy_kind if rl_policy else None,
    }


class ModeRequest(BaseModel):
    mode: str


def _require_simulator() -> MarketSimulator:
    if simulator is None:
        raise HTTPException(status_code=409, detail="No active simulation")
    return simulator


def _stop_abides() -> None:
    global abides_simulator, _abides_task
    if abides_simulator and abides_simulator.running:
        abides_simulator.running = False
    if _abides_task:
        _abides_task.cancel()
        _abides_task = None


def _depth_profile_from_stock_info(info) -> dict:
    volumes = [float(value) for value in getattr(info, "volumes", []) if value is not None]
    avg_volume = sum(volumes) / max(1, len(volumes)) if volumes else 50_000.0
    level_size = max(50, min(5_000, int(avg_volume * 0.002)))
    return {
        "source": "ohlcv",
        "levels": 10,
        "level_size": level_size,
        "tick_spacing": 0.01,
        "spread_multiplier": 1.0,
        "avg_volume": round(avg_volume, 2),
        "method": "synthetic depth calibrated from OHLCV volume; not historical L2",
    }


def _record_warning_event(event: dict) -> None:
    _warning_timeline.append(event)
    if len(_warning_timeline) > 500:
        del _warning_timeline[:-500]


@app.post("/api/simulation/mode")
async def set_simulation_mode(request: ModeRequest):
    if request.mode not in ["SANDBOX", "LIVE_SHADOW"]:
        raise HTTPException(status_code=400, detail="Invalid mode")
    if request.mode == "LIVE_SHADOW":
        raise HTTPException(
            status_code=400,
            detail="Live-shadow mode requires launching a Groww or Upstox data source.",
        )

    config.simulation_mode = request.mode
    if simulator:
        simulator.mode = request.mode

    return {"status": "mode_updated", "mode": request.mode}


@app.post("/api/simulation/start")
async def start_simulation():
    global simulator, _sim_task

    if simulator and simulator.running:
        return {"status": "already_running", "step": simulator.step_count}

    _stop_abides()
    config.simulation_mode = "SANDBOX"

    large_order_detector.reset()
    if rl_policy:
        rl_policy.reload()

    scenario = get_scenario_config("normal")
    agents = (
        ([RLAgent("RL_MM", initial_capital=100000.0)] if rl_policy and rl_policy.ready else [])
        + create_sandbox_agents("balanced", scenario=scenario)
    )

    simulator = MarketSimulator(
        agents,
        initial_price=config.initial_price,
        duration_seconds=config.simulation_duration,
        mode="SANDBOX",
        scenario=scenario.name,
    )

    # Run simulation in background task
    _sim_task = asyncio.create_task(_run_simulation_loop())

    return {
        "status": "started",
        "agents": len(agents),
        "initial_price": config.initial_price,
        "rl_policy_active": bool(rl_policy and rl_policy.ready),
    }


@app.post("/api/simulation/stop")
async def stop_simulation():
    global simulator, _sim_task, _warning_timeline

    if simulator:
        simulator.stop()
    if _sim_task:
        _sim_task.cancel()
        _sim_task = None

    _stop_abides()

    large_order_detector.reset()
    _warning_timeline = []
    config.simulation_mode = "SANDBOX"

    return {"status": "stopped"}


@app.get("/api/prediction/liquidity")
async def get_liquidity_prediction():
    active_simulator = _require_simulator()
    state = active_simulator.get_market_state()
    return liquidity_predictor.predict(state)


@app.get("/api/prediction/large-order")
async def get_large_order_detection():
    active_simulator = _require_simulator()
    state = active_simulator.get_market_state()
    detection = large_order_detector.detect(state)
    return detection or {"pattern": None, "message": "No large orders detected"}


@app.get("/api/agents/metrics")
async def get_agent_metrics():
    active_simulator = _require_simulator()
    metrics = {}
    for agent in active_simulator.agents:
        metrics[agent.agent_id] = agent.get_metrics(active_simulator.current_price)
    return metrics


@app.get("/api/market/snapshot")
async def get_market_snapshot():
    active_simulator = _require_simulator()
    state = active_simulator.get_market_state()
    return {
        "price": state["current_price"],
        "mid_price": state["mid_price"],
        "spread": state["spread"],
        "best_bid": state["best_bid"],
        "best_ask": state["best_ask"],
        "depth": state["total_depth"],
        "order_book": {
            "bids": state["bid_levels"],
            "asks": state["ask_levels"],
        },
        "volatility": state["volatility"],
        "step": state["step"],
    }


@app.get("/api/simulation/export")
async def export_simulation_run():
    active_simulator = _require_simulator()
    return active_simulator.get_export_snapshot(_warning_timeline)


# ── Sandbox Endpoints ──────────────────────────────────────────────────────


@app.get("/api/sandbox/presets")
async def list_sandbox_presets():
    return get_sandbox_presets()


@app.get("/api/sandbox/scenarios")
async def list_sandbox_scenarios():
    return {"scenarios": list_scenarios()}


@app.get("/api/sandbox/capabilities")
async def get_sandbox_capabilities():
    return {"abides": ABIDES_AVAILABLE}


class SandboxCreateRequest(BaseModel):
    preset: str = "balanced"
    initial_price: float = 100.0
    oracle_enabled: bool = False
    oracle_kappa: float = 0.05
    oracle_sigma: float = 0.02
    latency_mode: str = "deterministic"
    speed: float = 1.0
    custom_agents: Optional[dict] = None
    scenario: str = "normal"


class AbidesSandboxCreateRequest(BaseModel):
    initial_price: float = 100.0
    oracle_enabled: bool = True
    oracle_kappa: float = 0.05
    oracle_sigma: float = 0.02
    latency_mode: str = "deterministic"
    speed: float = 1.0
    market_makers: int = 1
    noise_agents: int = 2
    informed_agents: int = 1


@app.post("/api/sandbox/create")
async def create_sandbox(request: SandboxCreateRequest):
    global simulator, _sim_task

    if simulator and simulator.running:
        simulator.stop()
        if _sim_task:
            _sim_task.cancel()

    _stop_abides()
    config.simulation_mode = "SANDBOX"

    large_order_detector.reset()
    if rl_policy:
        rl_policy.reload()

    scenario = get_scenario_config(request.scenario)
    agents = create_sandbox_agents(request.preset, request.custom_agents, scenario=scenario)
    if rl_policy and rl_policy.ready:
        agents.append(RLAgent("RL_MM", initial_capital=100000.0))

    oracle_cfg = OracleConfig(
        r_bar=request.initial_price, kappa=request.oracle_kappa,
        sigma_s=request.oracle_sigma * scenario.oracle_sigma_multiplier,
        enabled=request.oracle_enabled,
    )
    mode_map = {"zero": LatencyMode.ZERO, "deterministic": LatencyMode.DETERMINISTIC, "cubic": LatencyMode.CUBIC}
    latency_cfg = LatencyConfig(mode=mode_map.get(request.latency_mode, LatencyMode.DETERMINISTIC))

    simulator = MarketSimulator(
        agents, initial_price=request.initial_price,
        duration_seconds=config.simulation_duration, mode="SANDBOX",
        oracle_config=oracle_cfg, latency_config=latency_cfg, speed_multiplier=request.speed,
        scenario=scenario.name,
    )
    _sim_task = asyncio.create_task(_run_simulation_loop())
    return {"status": "started", "preset": request.preset, "agents": len(agents),
            "oracle_enabled": request.oracle_enabled, "speed": request.speed,
            "scenario": scenario.name}


@app.post("/api/sandbox/abides/create")
async def create_abides_sandbox(request: AbidesSandboxCreateRequest):
    global abides_simulator, _abides_task

    if not ABIDES_AVAILABLE:
        raise HTTPException(status_code=501, detail="ABIDES module not available")

    if abides_simulator and abides_simulator.running:
        abides_simulator.running = False
        if _abides_task:
            _abides_task.cancel()

    if simulator and simulator.running:
        simulator.stop()
        if _sim_task:
            _sim_task.cancel()

    market_maker_count = max(0, request.market_makers)
    noise_agent_count = max(0, request.noise_agents)
    informed_agent_count = max(0, request.informed_agents)
    oracle_auto_enabled = not request.oracle_enabled and informed_agent_count > 0
    abides_oracle_enabled = request.oracle_enabled or oracle_auto_enabled

    oracle_cfg = OracleConfig(
        r_bar=request.initial_price,
        kappa=request.oracle_kappa,
        sigma_s=request.oracle_sigma,
        enabled=abides_oracle_enabled,
    )
    mode_map = {"zero": LatencyMode.ZERO, "deterministic": LatencyMode.DETERMINISTIC, "cubic": LatencyMode.CUBIC}
    latency_cfg = LatencyConfig(mode=mode_map.get(request.latency_mode, LatencyMode.DETERMINISTIC))

    abides_simulator = AbidesSimulation(
        oracle_config=oracle_cfg,
        latency_config=latency_cfg,
        speed_multiplier=request.speed,
    )
    exchange = AbidesExchangeAgent(initial_price=request.initial_price)
    abides_simulator.set_exchange(exchange)

    for idx in range(market_maker_count):
        abides_simulator.register_agent(AbidesMarketMakerAgent(f"AB_MM_{idx+1}", wakeup_interval=0.5))
    for idx in range(noise_agent_count):
        abides_simulator.register_agent(AbidesNoiseAgent(f"AB_NOISE_{idx+1}", wakeup_interval=0.4, order_rate=0.8))
    for idx in range(informed_agent_count):
        abides_simulator.register_agent(AbidesInformedAgent(f"AB_INF_{idx+1}", wakeup_interval=0.7, mispricing_threshold=0.15))

    _abides_task = asyncio.create_task(_run_abides_loop())
    return {
        "status": "started",
        "engine": "ABIDES",
        "oracle_enabled": abides_oracle_enabled,
        "oracle_auto_enabled": oracle_auto_enabled,
        "speed": request.speed,
        "agents": len(abides_simulator.agents),
    }


@app.post("/api/sandbox/abides/stop")
async def stop_abides_sandbox():
    _stop_abides()
    return {"status": "stopped"}


@app.get("/api/sandbox/abides/status")
async def abides_status():
    return {
        "available": ABIDES_AVAILABLE,
        "running": bool(abides_simulator and abides_simulator.running),
        "step": abides_simulator.step_count if abides_simulator else 0,
    }


class SpeedRequest(BaseModel):
    speed: float


@app.put("/api/sandbox/speed")
async def set_sandbox_speed(request: SpeedRequest):
    if simulator is None:
        return {"error": "No active simulation"}
    simulator.speed_multiplier = max(0.1, min(20.0, request.speed))
    return {"speed": simulator.speed_multiplier}


@app.put("/api/sandbox/abides/speed")
async def set_abides_speed(request: SpeedRequest):
    if abides_simulator is None:
        return {"error": "No active ABIDES simulation"}
    abides_simulator.speed_multiplier = max(0.1, min(20.0, request.speed))
    return {"speed": abides_simulator.speed_multiplier}


@app.get("/api/sandbox/oracle")
async def get_oracle_data():
    if simulator is None:
        return {"error": "No active simulation"}
    return {**simulator.oracle.describe(), "recent_history": simulator.oracle.get_recent_history(240)}


# ── Stock Replay Endpoints ──────────────────────────────────────────────────


@app.get("/api/sandbox/stocks/popular")
async def list_popular_stocks():
    return POPULAR_TICKERS


class StockFetchRequest(BaseModel):
    ticker: str
    period: str = "3mo"
    interval: str = "1d"


@app.post("/api/sandbox/stock/fetch")
async def fetch_stock_data(request: StockFetchRequest):
    try:
        info = fetch_stock(ticker=request.ticker, period=request.period, interval=request.interval)
        return {"ticker": info.ticker, "name": info.name, "currency": info.currency,
                "last_close": info.last_close, "period_start": info.period_start,
                "period_end": info.period_end, "bars": info.bars,
                "realized_vol": info.realized_vol, "mean_return": info.mean_return,
                "price_preview": info.prices[-60:]}
    except (ValueError, Exception) as e:
        return {"error": str(e)}


class StockReplayRequest(BaseModel):
    ticker: str
    period: str = "3mo"
    interval: str = "1d"
    preset: str = "balanced"
    custom_agents: Optional[dict] = None
    latency_mode: str = "deterministic"
    speed: float = 1.0
    scenario: str = "normal"


class GrowwFetchRequest(BaseModel):
    groww_symbol: str = "NSE-RELIANCE"
    exchange: str = "NSE"
    segment: str = "CASH"
    start_time: str = "2025-09-24 09:15:00"
    end_time: str = "2025-09-24 15:30:00"
    candle_interval: str = "MIN_30"


class GrowwReplayRequest(GrowwFetchRequest):
    preset: str = "balanced"
    custom_agents: Optional[dict] = None
    latency_mode: str = "deterministic"
    speed: float = 1.0
    scenario: str = "normal"


class GrowwQuoteRequest(BaseModel):
    groww_symbol: str = "NSE-RELIANCE"
    exchange: str = "NSE"
    segment: str = "CASH"


class GrowwLiveRequest(GrowwQuoteRequest):
    preset: str = "balanced"
    custom_agents: Optional[dict] = None
    latency_mode: str = "deterministic"
    speed: float = 1.0
    poll_interval_seconds: int = 5
    scenario: str = "normal"


class UpstoxFetchRequest(BaseModel):
    instrument_key: str = "NSE_EQ|INE002A01018"
    unit: str = "minutes"
    interval: str = "30"
    from_date: Optional[str] = "2025-01-01"
    to_date: str = "2025-01-01"


class UpstoxReplayRequest(UpstoxFetchRequest):
    preset: str = "balanced"
    custom_agents: Optional[dict] = None
    latency_mode: str = "deterministic"
    speed: float = 1.0
    scenario: str = "normal"


class UpstoxLtpRequest(BaseModel):
    instrument_key: str = "NSE_EQ|INE002A01018"


class UpstoxLiveRequest(UpstoxLtpRequest):
    preset: str = "balanced"
    custom_agents: Optional[dict] = None
    latency_mode: str = "deterministic"
    speed: float = 1.0
    poll_interval_seconds: int = 5
    scenario: str = "normal"


@app.post("/api/sandbox/stock/replay")
async def start_stock_replay(request: StockReplayRequest):
    global simulator, _sim_task
    try:
        info = fetch_stock(ticker=request.ticker, period=request.period, interval=request.interval)
    except (ValueError, Exception) as e:
        return {"error": str(e)}

    if simulator and simulator.running:
        simulator.stop()
        if _sim_task:
            _sim_task.cancel()
    _stop_abides()
    large_order_detector.reset()
    config.simulation_mode = "SANDBOX"

    oracle_path = build_oracle_path(info, target_steps=500)
    initial_price = float(info.prices[0])
    scenario = get_scenario_config(request.scenario)
    depth_profile = _depth_profile_from_stock_info(info)
    oracle_cfg = OracleConfig(r_bar=initial_price, kappa=0.05,
                              sigma_s=max(0.001, info.realized_vol / 252) * scenario.oracle_sigma_multiplier,
                              enabled=True, replay_path=oracle_path)
    mode_map = {"zero": LatencyMode.ZERO, "deterministic": LatencyMode.DETERMINISTIC, "cubic": LatencyMode.CUBIC}
    latency_cfg = LatencyConfig(mode=mode_map.get(request.latency_mode, LatencyMode.DETERMINISTIC))
    agents = create_sandbox_agents(request.preset, request.custom_agents, scenario=scenario)

    simulator = MarketSimulator(
        agents, initial_price=initial_price, duration_seconds=config.simulation_duration,
        mode="SANDBOX", oracle_config=oracle_cfg, latency_config=latency_cfg,
        speed_multiplier=request.speed, scenario=scenario.name, depth_profile=depth_profile,
    )
    _sim_task = asyncio.create_task(_run_simulation_loop())
    return {"status": "started", "ticker": info.ticker, "name": info.name,
            "initial_price": initial_price, "bars": info.bars,
            "realized_vol": info.realized_vol, "agents": len(agents),
            "scenario": scenario.name}


@app.post("/api/live-shadow/groww/fetch")
async def fetch_groww_data(request: GrowwFetchRequest):
    try:
        symbol = normalize_groww_symbol(request.exchange, request.groww_symbol)
        info = fetch_groww_historical_stock(
            exchange=request.exchange,
            segment=request.segment,
            groww_symbol=symbol,
            start_time=request.start_time,
            end_time=request.end_time,
            candle_interval=request.candle_interval,
        )
        return {
            "provider": "groww",
            "source": "historical",
            "status": "connected",
            "mode": "LIVE_SHADOW",
            "groww_symbol": info.ticker,
            "name": info.name,
            "currency": info.currency,
            "last_close": info.last_close,
            "period_start": info.period_start,
            "period_end": info.period_end,
            "bars": info.bars,
            "realized_vol": info.realized_vol,
            "mean_return": info.mean_return,
            "price_preview": info.prices[-60:],
        }
    except (GrowwCredentialsError, GrowwSdkMissingError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GrowwProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Groww historical fetch failed: {exc}") from exc


@app.post("/api/live-shadow/groww/replay")
async def start_groww_replay(request: GrowwReplayRequest):
    global simulator, _sim_task

    try:
        symbol = normalize_groww_symbol(request.exchange, request.groww_symbol)
        info = fetch_groww_historical_stock(
            exchange=request.exchange,
            segment=request.segment,
            groww_symbol=symbol,
            start_time=request.start_time,
            end_time=request.end_time,
            candle_interval=request.candle_interval,
        )
    except (GrowwCredentialsError, GrowwSdkMissingError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GrowwProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Groww historical replay failed: {exc}") from exc

    if simulator and simulator.running:
        simulator.stop()
        if _sim_task:
            _sim_task.cancel()
    _stop_abides()
    large_order_detector.reset()

    config.simulation_mode = "LIVE_SHADOW"
    scenario = get_scenario_config(request.scenario)
    depth_profile = _depth_profile_from_stock_info(info)
    oracle_path = build_oracle_path(info, target_steps=500)
    initial_price = float(info.prices[0])
    oracle_cfg = OracleConfig(
        r_bar=initial_price,
        kappa=0.05,
        sigma_s=max(0.001, info.realized_vol / 252) * scenario.oracle_sigma_multiplier,
        enabled=True,
        replay_path=oracle_path,
    )
    mode_map = {"zero": LatencyMode.ZERO, "deterministic": LatencyMode.DETERMINISTIC, "cubic": LatencyMode.CUBIC}
    latency_cfg = LatencyConfig(mode=mode_map.get(request.latency_mode, LatencyMode.DETERMINISTIC))
    agents = create_sandbox_agents(request.preset, request.custom_agents, scenario=scenario)

    simulator = MarketSimulator(
        agents,
        initial_price=initial_price,
        duration_seconds=config.simulation_duration,
        mode="LIVE_SHADOW",
        oracle_config=oracle_cfg,
        latency_config=latency_cfg,
        speed_multiplier=request.speed,
        scenario=scenario.name,
        depth_profile=depth_profile,
    )
    replay_steps = len(oracle_path)
    simulator.data_source = {
        "provider": "groww",
        "source": "historical_replay",
        "status": "connected",
        "groww_symbol": info.ticker,
        "exchange": request.exchange.upper(),
        "segment": request.segment.upper(),
        "candle_interval": request.candle_interval,
        "depth_source": "calibrated_from_ohlcv",
        "depth_model": depth_profile,
        "scenario": scenario.name,
        "bars": info.bars,
        "replay_steps": replay_steps,
        "period_start": info.period_start,
        "period_end": info.period_end,
    }
    _sim_task = asyncio.create_task(_run_simulation_loop())
    return {
        "status": "started",
        "mode": "LIVE_SHADOW",
        "provider": "groww",
        "source": "historical_replay",
        "groww_symbol": info.ticker,
        "initial_price": initial_price,
        "bars": info.bars,
        "replay_steps": replay_steps,
        "realized_vol": info.realized_vol,
        "agents": len(agents),
        "speed": request.speed,
        "scenario": scenario.name,
    }


@app.post("/api/live-shadow/groww/quote")
async def fetch_groww_quote_data(request: GrowwQuoteRequest):
    try:
        symbol = normalize_groww_symbol(request.exchange, request.groww_symbol)
        quote = fetch_groww_quote(
            exchange=request.exchange,
            segment=request.segment,
            groww_symbol=symbol,
        )
    except (GrowwCredentialsError, GrowwSdkMissingError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GrowwProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Groww live quote fetch failed: {exc}") from exc

    return {
        "provider": "groww",
        "source": "live_depth",
        "status": "connected",
        "mode": "LIVE_SHADOW",
        **asdict(quote),
    }


@app.post("/api/live-shadow/groww/live")
async def start_groww_live_shadow(request: GrowwLiveRequest):
    global simulator, _sim_task

    try:
        symbol = normalize_groww_symbol(request.exchange, request.groww_symbol)
        initial_quote = fetch_groww_quote(
            exchange=request.exchange,
            segment=request.segment,
            groww_symbol=symbol,
        )
    except (GrowwCredentialsError, GrowwSdkMissingError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GrowwProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Groww live quote start failed: {exc}") from exc

    if simulator and simulator.running:
        simulator.stop()
        if _sim_task:
            _sim_task.cancel()
    _stop_abides()
    large_order_detector.reset()

    config.simulation_mode = "LIVE_SHADOW"
    initial_price = float(initial_quote.last_price)
    scenario = get_scenario_config(request.scenario)
    oracle_cfg = OracleConfig(r_bar=initial_price, enabled=False)
    mode_map = {"zero": LatencyMode.ZERO, "deterministic": LatencyMode.DETERMINISTIC, "cubic": LatencyMode.CUBIC}
    latency_cfg = LatencyConfig(mode=mode_map.get(request.latency_mode, LatencyMode.DETERMINISTIC))
    agents = create_sandbox_agents(request.preset, request.custom_agents, scenario=scenario)
    poll_interval = min(60, max(1, int(request.poll_interval_seconds)))

    simulator = MarketSimulator(
        agents,
        initial_price=initial_price,
        duration_seconds=config.simulation_duration,
        mode="LIVE_SHADOW",
        oracle_config=oracle_cfg,
        latency_config=latency_cfg,
        speed_multiplier=request.speed,
        scenario=scenario.name,
    )
    simulator.data_source = {
        "provider": "groww",
        "source": "live_depth",
        "status": "connected",
        "poll_interval_seconds": poll_interval,
        "scenario": scenario.name,
        **asdict(initial_quote),
        "depth_source": initial_quote.depth_source or "synthetic_fallback",
    }

    def _groww_live_quote_provider():
        quote = fetch_groww_quote(
            exchange=request.exchange,
            segment=request.segment,
            groww_symbol=symbol,
        )
        return asdict(quote)

    simulator.set_external_price_provider(_groww_live_quote_provider, poll_interval_seconds=poll_interval)
    _sim_task = asyncio.create_task(_run_simulation_loop())

    return {
        "status": "started",
        "mode": "LIVE_SHADOW",
        "provider": "groww",
        "source": "live_depth",
        "groww_symbol": initial_quote.groww_symbol,
        "initial_price": initial_price,
        "last_price": initial_quote.last_price,
        "depth_source": initial_quote.depth_source or "synthetic_fallback",
        "poll_interval_seconds": poll_interval,
        "agents": len(agents),
        "speed": request.speed,
        "scenario": scenario.name,
    }


@app.post("/api/live-shadow/upstox/fetch")
async def fetch_upstox_data(request: UpstoxFetchRequest):
    try:
        instrument_key = normalize_upstox_instrument_key(request.instrument_key)
        info = fetch_upstox_historical_stock(
            instrument_key=instrument_key,
            unit=request.unit,
            interval=request.interval,
            from_date=request.from_date,
            to_date=request.to_date,
        )
        return {
            "provider": "upstox",
            "source": "historical",
            "status": "connected",
            "mode": "LIVE_SHADOW",
            "instrument_key": info.ticker,
            "name": info.name,
            "currency": info.currency,
            "last_close": info.last_close,
            "period_start": info.period_start,
            "period_end": info.period_end,
            "bars": info.bars,
            "realized_vol": info.realized_vol,
            "mean_return": info.mean_return,
            "price_preview": info.prices[-60:],
        }
    except UpstoxCredentialsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UpstoxProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstox historical fetch failed: {exc}") from exc


@app.post("/api/live-shadow/upstox/replay")
async def start_upstox_replay(request: UpstoxReplayRequest):
    global simulator, _sim_task

    try:
        instrument_key = normalize_upstox_instrument_key(request.instrument_key)
        info = fetch_upstox_historical_stock(
            instrument_key=instrument_key,
            unit=request.unit,
            interval=request.interval,
            from_date=request.from_date,
            to_date=request.to_date,
        )
    except UpstoxCredentialsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UpstoxProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstox historical replay failed: {exc}") from exc

    if simulator and simulator.running:
        simulator.stop()
        if _sim_task:
            _sim_task.cancel()
    _stop_abides()
    large_order_detector.reset()

    config.simulation_mode = "LIVE_SHADOW"
    scenario = get_scenario_config(request.scenario)
    depth_profile = _depth_profile_from_stock_info(info)
    oracle_path = build_oracle_path(info, target_steps=500)
    initial_price = float(info.prices[0])
    oracle_cfg = OracleConfig(
        r_bar=initial_price,
        kappa=0.05,
        sigma_s=max(0.001, info.realized_vol / 252) * scenario.oracle_sigma_multiplier,
        enabled=True,
        replay_path=oracle_path,
    )
    mode_map = {"zero": LatencyMode.ZERO, "deterministic": LatencyMode.DETERMINISTIC, "cubic": LatencyMode.CUBIC}
    latency_cfg = LatencyConfig(mode=mode_map.get(request.latency_mode, LatencyMode.DETERMINISTIC))
    agents = create_sandbox_agents(request.preset, request.custom_agents, scenario=scenario)

    simulator = MarketSimulator(
        agents,
        initial_price=initial_price,
        duration_seconds=config.simulation_duration,
        mode="LIVE_SHADOW",
        oracle_config=oracle_cfg,
        latency_config=latency_cfg,
        speed_multiplier=request.speed,
        scenario=scenario.name,
        depth_profile=depth_profile,
    )
    replay_steps = len(oracle_path)
    simulator.data_source = {
        "provider": "upstox",
        "source": "historical_replay",
        "status": "connected",
        "instrument_key": info.ticker,
        "unit": request.unit.lower(),
        "interval": request.interval,
        "depth_source": "calibrated_from_ohlcv",
        "depth_model": depth_profile,
        "scenario": scenario.name,
        "bars": info.bars,
        "replay_steps": replay_steps,
        "period_start": info.period_start,
        "period_end": info.period_end,
    }
    _sim_task = asyncio.create_task(_run_simulation_loop())
    return {
        "status": "started",
        "mode": "LIVE_SHADOW",
        "provider": "upstox",
        "source": "historical_replay",
        "instrument_key": info.ticker,
        "initial_price": initial_price,
        "bars": info.bars,
        "replay_steps": replay_steps,
        "realized_vol": info.realized_vol,
        "agents": len(agents),
        "speed": request.speed,
        "scenario": scenario.name,
    }


@app.get("/api/live-shadow/upstox/instruments")
async def search_upstox_instrument_data(
    query: str,
    exchanges: str = "NSE",
    segments: str = "EQ",
    page_number: int = 1,
    records: int = 10,
):
    try:
        instruments = search_upstox_instruments(
            query=query,
            exchanges=exchanges,
            segments=segments,
            page_number=page_number,
            records=records,
        )
    except UpstoxCredentialsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UpstoxProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstox instrument search failed: {exc}") from exc

    return {
        "provider": "upstox",
        "source": "instrument_search",
        "status": "connected",
        "query": query,
        "results": [asdict(instrument) for instrument in instruments],
    }


@app.post("/api/live-shadow/upstox/ltp")
async def fetch_upstox_ltp_data(request: UpstoxLtpRequest):
    try:
        instrument_key = normalize_upstox_instrument_key(request.instrument_key)
        quote = fetch_upstox_ltp_quote(instrument_key=instrument_key)
    except UpstoxCredentialsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UpstoxProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstox LTP fetch failed: {exc}") from exc

    return {
        "provider": "upstox",
        "source": "live_ltp",
        "status": "connected",
        "mode": "LIVE_SHADOW",
        **asdict(quote),
    }


@app.post("/api/live-shadow/upstox/live")
async def start_upstox_live_shadow(request: UpstoxLiveRequest):
    global simulator, _sim_task

    try:
        instrument_key = normalize_upstox_instrument_key(request.instrument_key)
        initial_quote = fetch_upstox_full_quote(instrument_key=instrument_key)
    except UpstoxCredentialsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UpstoxProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstox live depth start failed: {exc}") from exc

    if simulator and simulator.running:
        simulator.stop()
        if _sim_task:
            _sim_task.cancel()
    _stop_abides()
    large_order_detector.reset()

    config.simulation_mode = "LIVE_SHADOW"
    initial_price = float(initial_quote.last_price)
    scenario = get_scenario_config(request.scenario)
    oracle_cfg = OracleConfig(r_bar=initial_price, enabled=False)
    mode_map = {"zero": LatencyMode.ZERO, "deterministic": LatencyMode.DETERMINISTIC, "cubic": LatencyMode.CUBIC}
    latency_cfg = LatencyConfig(mode=mode_map.get(request.latency_mode, LatencyMode.DETERMINISTIC))
    agents = create_sandbox_agents(request.preset, request.custom_agents, scenario=scenario)
    poll_interval = min(60, max(1, int(request.poll_interval_seconds)))

    simulator = MarketSimulator(
        agents,
        initial_price=initial_price,
        duration_seconds=config.simulation_duration,
        mode="LIVE_SHADOW",
        oracle_config=oracle_cfg,
        latency_config=latency_cfg,
        speed_multiplier=request.speed,
        scenario=scenario.name,
    )
    simulator.data_source = {
        "provider": "upstox",
        "source": "live_depth",
        "status": "connected",
        "poll_interval_seconds": poll_interval,
        "scenario": scenario.name,
        **asdict(initial_quote),
        "depth_source": initial_quote.depth_source or "synthetic_fallback",
    }

    def _upstox_live_quote_provider():
        quote = fetch_upstox_full_quote(instrument_key=instrument_key)
        return asdict(quote)

    simulator.set_external_price_provider(_upstox_live_quote_provider, poll_interval_seconds=poll_interval)
    _sim_task = asyncio.create_task(_run_simulation_loop())

    return {
        "status": "started",
        "mode": "LIVE_SHADOW",
        "provider": "upstox",
        "source": "live_depth",
        "instrument_key": initial_quote.instrument_key,
        "initial_price": initial_price,
        "last_price": initial_quote.last_price,
        "depth_source": initial_quote.depth_source or "synthetic_fallback",
        "poll_interval_seconds": poll_interval,
        "agents": len(agents),
        "speed": request.speed,
        "scenario": scenario.name,
    }


# ── WebSocket ───────────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, receive any client messages
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


# ── Simulation Loop ─────────────────────────────────────────────────────────


def _build_market_update(
    *,
    state: dict,
    liquidity_prediction: Optional[dict],
    large_order_detection: Optional[dict],
    agent_metrics: dict,
    active_simulator: MarketSimulator,
) -> dict:
    update = {
        "type": "market_update",
        "timestamp": state["current_time"],
        "price": state["current_price"],
        "spread": state["spread"],
        "depth": state["total_depth"],
        "order_book": {"bids": state["bid_levels"][:10], "asks": state["ask_levels"][:10]},
        "liquidity_prediction": liquidity_prediction,
        "large_order_detection": large_order_detection,
        "agent_metrics": agent_metrics,
        "step": state["step"],
        "volatility": state["volatility"],
        "mode": active_simulator.mode,
        "speed": getattr(active_simulator, "speed_multiplier", 1.0),
    }

    if "oracle" in state:
        update["oracle"] = state["oracle"]

    data_source = getattr(active_simulator, "data_source", None)
    if data_source:
        update["data_source"] = data_source

    return update


async def _run_simulation_loop():
    """Run the simulation and broadcast updates via WebSocket."""
    global simulator

    if simulator is None:
        return

    simulator.running = True
    logger.info("Simulation loop started")

    try:
        while simulator.running and simulator.current_time < simulator.duration_seconds:
            if rl_policy and rl_policy.ready:
                try:
                    rl_policy.prepare_step(simulator)
                except Exception as exc:
                    logger.error(f"RL policy inference failed: {exc}")

            state = simulator.step()

            liquidity_pred = liquidity_predictor.predict(state)
            large_order_det = large_order_detector.detect(state)
            if liquidity_pred and liquidity_pred.get("warning_level") not in {None, "safe"}:
                _record_warning_event({
                    "timestamp": state.get("current_time", 0.0),
                    "detector": "liquidity_shock",
                    "warning_level": liquidity_pred.get("warning_level"),
                    "probability": liquidity_pred.get("probability"),
                    "health_score": liquidity_pred.get("health_score"),
                    "scenario": state.get("scenario", {}).get("name"),
                })
            if large_order_det:
                _record_warning_event({
                    "timestamp": state.get("current_time", 0.0),
                    "detector": "large_order",
                    "pattern": large_order_det.get("pattern"),
                    "side": large_order_det.get("side"),
                    "confidence": large_order_det.get("confidence"),
                    "estimated_size": large_order_det.get("estimated_size"),
                    "scenario": state.get("scenario", {}).get("name"),
                })

            agent_metrics = {}
            for agent in simulator.agents:
                m = agent.get_metrics(simulator.current_price)
                agent_metrics[agent.agent_id] = {
                    "total_pnl": m["total_pnl"], "realized_pnl": m["realized_pnl"],
                    "unrealized_pnl": m["unrealized_pnl"], "sharpe_ratio": m["sharpe_ratio"],
                    "agent_type": m["agent_type"], "position": m["position"],
                    "num_trades": m["num_trades"],
                }

            update = _build_market_update(
                state=state,
                liquidity_prediction=liquidity_pred,
                large_order_detection=large_order_det,
                agent_metrics=agent_metrics,
                active_simulator=simulator,
            )

            if manager.client_count > 0:
                await manager.broadcast(update)

            sleep_time = max(0.02, 0.1 / getattr(simulator, 'speed_multiplier', 1.0))
            await asyncio.sleep(sleep_time)

    except asyncio.CancelledError:
        logger.info("Simulation loop cancelled")
    except Exception as e:
        logger.error(f"Simulation loop error: {e}")
    finally:
        if simulator:
            simulator.running = False
        logger.info("Simulation loop ended")


async def _run_abides_loop():
    """Run the ABIDES simulation and broadcast updates via WebSocket."""
    global abides_simulator

    if abides_simulator is None:
        return

    if not abides_simulator.running:
        abides_simulator.initialize()
    logger.info("ABIDES loop started")

    try:
        while abides_simulator.running:
            state = abides_simulator.step(step_seconds=1.0)

            agent_metrics = {}
            for agent in abides_simulator.agents.values():
                m = agent.get_metrics(state.get("mid_price") or state.get("price") or 0.0)
                agent_metrics[agent.agent_id] = {
                    "total_pnl": m["total_pnl"],
                    "realized_pnl": m["realized_pnl"],
                    "unrealized_pnl": m["unrealized_pnl"],
                    "sharpe_ratio": m["sharpe_ratio"],
                    "agent_type": m["agent_type"],
                    "position": m["position"],
                    "num_trades": m["num_trades"],
                }

            update = {
                "type": "abides_update",
                "timestamp": state.get("current_time", 0.0),
                "price": state.get("price"),
                "spread": state.get("spread"),
                "depth": state.get("total_depth"),
                "order_book": {
                    "bids": state.get("bid_levels", [])[:10],
                    "asks": state.get("ask_levels", [])[:10],
                },
                "agent_metrics": agent_metrics,
                "step": state.get("step", 0),
                "volatility": 0.0,
                "mode": "SANDBOX",
                "engine": "ABIDES",
                "speed": abides_simulator.speed_multiplier,
            }

            if state.get("oracle"):
                update["oracle"] = state.get("oracle")

            if manager.client_count > 0:
                await manager.broadcast(update)

            sleep_time = max(0.05, 0.2 / abides_simulator.speed_multiplier)
            await asyncio.sleep(sleep_time)

    except asyncio.CancelledError:
        logger.info("ABIDES loop cancelled")
    except Exception as exc:
        logger.error(f"ABIDES loop error: {exc}")
    finally:
        if abides_simulator:
            abides_simulator.running = False
        logger.info("ABIDES loop ended")
