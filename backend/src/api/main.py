"""FastAPI application — REST endpoints and WebSocket for SENTINEL."""

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Iterable, Optional
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

LATENCY_MODES = {
    "zero": LatencyMode.ZERO,
    "deterministic": LatencyMode.DETERMINISTIC,
    "cubic": LatencyMode.CUBIC,
}

AGENT_METRIC_FIELDS = (
    "total_pnl",
    "realized_pnl",
    "unrealized_pnl",
    "sharpe_ratio",
    "agent_type",
    "position",
    "num_trades",
)


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
    native_active, abides_active, active_engine = _simulation_activity()
    return {
        "status": "healthy",
        "simulation_active": native_active or abides_active,
        "connected_clients": manager.client_count,
        "mode": simulator.mode if simulator else config.simulation_mode,
        "engine": active_engine,
        "abides": {
            "available": ABIDES_AVAILABLE,
            "running": abides_active,
            "step": abides_simulator.step_count if abides_simulator else 0,
        },
        "rl_policy_ready": rl_policy.ready if rl_policy else False,
        "rl_policy_kind": rl_policy.loaded_policy_kind if rl_policy else None,
    }


class ModeRequest(BaseModel):
    mode: str


def _require_simulator() -> MarketSimulator:
    if simulator is None:
        raise HTTPException(status_code=409, detail="No active simulation")
    return simulator


def _simulation_activity() -> tuple[bool, bool, str]:
    native_active = simulator is not None and simulator.running
    abides_active = abides_simulator is not None and abides_simulator.running
    active_engine = "ABIDES" if abides_active and not native_active else "SENTINEL"
    return native_active, abides_active, active_engine


def _get_export_source():
    return simulator if simulator is not None else abides_simulator


def _latency_config(latency_mode: str) -> LatencyConfig:
    return LatencyConfig(mode=LATENCY_MODES.get(latency_mode, LatencyMode.DETERMINISTIC))


def _clamp_poll_interval(seconds: int) -> int:
    return min(60, max(1, int(seconds)))


def _stop_native_simulation() -> None:
    global _sim_task
    if simulator and simulator.running:
        simulator.stop()
    if _sim_task:
        _sim_task.cancel()
        _sim_task = None


def _stop_abides() -> None:
    global abides_simulator, _abides_task
    if abides_simulator and abides_simulator.running:
        abides_simulator.running = False
    if _abides_task:
        _abides_task.cancel()
        _abides_task = None


def _prepare_simulator_replacement(mode: str, *, reload_rl: bool = False) -> None:
    _stop_native_simulation()
    _stop_abides()
    large_order_detector.reset()
    config.simulation_mode = mode
    if reload_rl and rl_policy:
        rl_policy.reload()


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


def _stock_info_payload(info) -> dict:
    return {
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


def _live_shadow_stock_response(provider: str, symbol_key: str, info) -> dict:
    return {
        "provider": provider,
        "source": "historical",
        "status": "connected",
        "mode": "LIVE_SHADOW",
        symbol_key: info.ticker,
        **_stock_info_payload(info),
    }


def _build_replay_components(info, scenario_name: str):
    scenario = get_scenario_config(scenario_name)
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
    return scenario, depth_profile, oracle_path, initial_price, oracle_cfg


def _historical_replay_data_source(
    *,
    provider: str,
    symbol_key: str,
    info,
    depth_profile: dict,
    scenario_name: str,
    replay_steps: int,
    extra: Optional[dict] = None,
) -> dict:
    payload = {
        "provider": provider,
        "source": "historical_replay",
        "status": "connected",
        symbol_key: info.ticker,
        "depth_source": "calibrated_from_ohlcv",
        "depth_model": depth_profile,
        "scenario": scenario_name,
        "bars": info.bars,
        "replay_steps": replay_steps,
        "period_start": info.period_start,
        "period_end": info.period_end,
    }
    if extra:
        payload.update(extra)
    return payload


def _historical_replay_response(
    *,
    provider: str,
    symbol_key: str,
    info,
    initial_price: float,
    replay_steps: int,
    agents_count: int,
    speed: float,
    scenario_name: str,
) -> dict:
    return {
        "status": "started",
        "mode": "LIVE_SHADOW",
        "provider": provider,
        "source": "historical_replay",
        symbol_key: info.ticker,
        "initial_price": initial_price,
        "bars": info.bars,
        "replay_steps": replay_steps,
        "realized_vol": info.realized_vol,
        "agents": agents_count,
        "speed": speed,
        "scenario": scenario_name,
    }


def _quote_depth_source(quote) -> str:
    return quote.depth_source or "synthetic_fallback"


def _live_depth_data_source(provider: str, quote, poll_interval: int, scenario_name: str) -> dict:
    return {
        "provider": provider,
        "source": "live_depth",
        "status": "connected",
        "poll_interval_seconds": poll_interval,
        "scenario": scenario_name,
        **asdict(quote),
        "depth_source": _quote_depth_source(quote),
    }


def _live_depth_response(
    *,
    provider: str,
    symbol_key: str,
    symbol_value: str,
    quote,
    initial_price: float,
    poll_interval: int,
    agents_count: int,
    speed: float,
    scenario_name: str,
) -> dict:
    return {
        "status": "started",
        "mode": "LIVE_SHADOW",
        "provider": provider,
        "source": "live_depth",
        symbol_key: symbol_value,
        "initial_price": initial_price,
        "last_price": quote.last_price,
        "depth_source": _quote_depth_source(quote),
        "poll_interval_seconds": poll_interval,
        "agents": agents_count,
        "speed": speed,
        "scenario": scenario_name,
    }


def _agent_metrics_for(agents: Iterable, price: float) -> dict:
    metrics = {}
    for agent in agents:
        values = agent.get_metrics(price)
        metrics[agent.agent_id] = {field: values[field] for field in AGENT_METRIC_FIELDS}
    return metrics


def _record_step_warnings(
    *,
    state: dict,
    liquidity_prediction: Optional[dict],
    large_order_detection: Optional[dict],
) -> None:
    scenario_name = state.get("scenario", {}).get("name")
    timestamp = state.get("current_time", 0.0)

    if liquidity_prediction and liquidity_prediction.get("warning_level") not in {None, "safe"}:
        _record_warning_event({
            "timestamp": timestamp,
            "detector": "liquidity_shock",
            "warning_level": liquidity_prediction.get("warning_level"),
            "probability": liquidity_prediction.get("probability"),
            "health_score": liquidity_prediction.get("health_score"),
            "scenario": scenario_name,
        })

    if large_order_detection:
        _record_warning_event({
            "timestamp": timestamp,
            "detector": "large_order",
            "pattern": large_order_detection.get("pattern"),
            "side": large_order_detection.get("side"),
            "confidence": large_order_detection.get("confidence"),
            "estimated_size": large_order_detection.get("estimated_size"),
            "scenario": scenario_name,
        })


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

    _prepare_simulator_replacement("SANDBOX", reload_rl=True)

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

    _stop_native_simulation()
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
    export_source = _get_export_source()
    if export_source is not None:
        return export_source.get_export_snapshot(_warning_timeline)
    raise HTTPException(status_code=409, detail="No active simulation")


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

    _prepare_simulator_replacement("SANDBOX", reload_rl=True)

    scenario = get_scenario_config(request.scenario)
    agents = create_sandbox_agents(request.preset, request.custom_agents, scenario=scenario)
    if rl_policy and rl_policy.ready:
        agents.append(RLAgent("RL_MM", initial_capital=100000.0))

    oracle_cfg = OracleConfig(
        r_bar=request.initial_price, kappa=request.oracle_kappa,
        sigma_s=request.oracle_sigma * scenario.oracle_sigma_multiplier,
        enabled=request.oracle_enabled,
    )
    latency_cfg = _latency_config(request.latency_mode)

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

    _stop_abides()
    _stop_native_simulation()

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
    latency_cfg = _latency_config(request.latency_mode)

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
        return {"ticker": info.ticker, **_stock_info_payload(info)}
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

    _prepare_simulator_replacement("SANDBOX")

    scenario, depth_profile, oracle_path, initial_price, oracle_cfg = _build_replay_components(
        info, request.scenario
    )
    latency_cfg = _latency_config(request.latency_mode)
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
        return _live_shadow_stock_response("groww", "groww_symbol", info)
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

    _prepare_simulator_replacement("LIVE_SHADOW")

    scenario, depth_profile, oracle_path, initial_price, oracle_cfg = _build_replay_components(
        info, request.scenario
    )
    latency_cfg = _latency_config(request.latency_mode)
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
    simulator.data_source = _historical_replay_data_source(
        provider="groww",
        symbol_key="groww_symbol",
        info=info,
        depth_profile=depth_profile,
        scenario_name=scenario.name,
        replay_steps=replay_steps,
        extra={
            "exchange": request.exchange.upper(),
            "segment": request.segment.upper(),
            "candle_interval": request.candle_interval,
        },
    )
    _sim_task = asyncio.create_task(_run_simulation_loop())
    return _historical_replay_response(
        provider="groww",
        symbol_key="groww_symbol",
        info=info,
        initial_price=initial_price,
        replay_steps=replay_steps,
        agents_count=len(agents),
        speed=request.speed,
        scenario_name=scenario.name,
    )


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

    _prepare_simulator_replacement("LIVE_SHADOW")

    initial_price = float(initial_quote.last_price)
    scenario = get_scenario_config(request.scenario)
    oracle_cfg = OracleConfig(r_bar=initial_price, enabled=False)
    latency_cfg = _latency_config(request.latency_mode)
    agents = create_sandbox_agents(request.preset, request.custom_agents, scenario=scenario)
    poll_interval = _clamp_poll_interval(request.poll_interval_seconds)

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
    simulator.data_source = _live_depth_data_source("groww", initial_quote, poll_interval, scenario.name)

    def _groww_live_quote_provider():
        quote = fetch_groww_quote(
            exchange=request.exchange,
            segment=request.segment,
            groww_symbol=symbol,
        )
        return asdict(quote)

    simulator.set_external_price_provider(_groww_live_quote_provider, poll_interval_seconds=poll_interval)
    _sim_task = asyncio.create_task(_run_simulation_loop())

    return _live_depth_response(
        provider="groww",
        symbol_key="groww_symbol",
        symbol_value=initial_quote.groww_symbol,
        quote=initial_quote,
        initial_price=initial_price,
        poll_interval=poll_interval,
        agents_count=len(agents),
        speed=request.speed,
        scenario_name=scenario.name,
    )


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
        return _live_shadow_stock_response("upstox", "instrument_key", info)
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

    _prepare_simulator_replacement("LIVE_SHADOW")

    scenario, depth_profile, oracle_path, initial_price, oracle_cfg = _build_replay_components(
        info, request.scenario
    )
    latency_cfg = _latency_config(request.latency_mode)
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
    simulator.data_source = _historical_replay_data_source(
        provider="upstox",
        symbol_key="instrument_key",
        info=info,
        depth_profile=depth_profile,
        scenario_name=scenario.name,
        replay_steps=replay_steps,
        extra={"unit": request.unit.lower(), "interval": request.interval},
    )
    _sim_task = asyncio.create_task(_run_simulation_loop())
    return _historical_replay_response(
        provider="upstox",
        symbol_key="instrument_key",
        info=info,
        initial_price=initial_price,
        replay_steps=replay_steps,
        agents_count=len(agents),
        speed=request.speed,
        scenario_name=scenario.name,
    )


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

    _prepare_simulator_replacement("LIVE_SHADOW")

    initial_price = float(initial_quote.last_price)
    scenario = get_scenario_config(request.scenario)
    oracle_cfg = OracleConfig(r_bar=initial_price, enabled=False)
    latency_cfg = _latency_config(request.latency_mode)
    agents = create_sandbox_agents(request.preset, request.custom_agents, scenario=scenario)
    poll_interval = _clamp_poll_interval(request.poll_interval_seconds)

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
    simulator.data_source = _live_depth_data_source("upstox", initial_quote, poll_interval, scenario.name)

    def _upstox_live_quote_provider():
        quote = fetch_upstox_full_quote(instrument_key=instrument_key)
        return asdict(quote)

    simulator.set_external_price_provider(_upstox_live_quote_provider, poll_interval_seconds=poll_interval)
    _sim_task = asyncio.create_task(_run_simulation_loop())

    return _live_depth_response(
        provider="upstox",
        symbol_key="instrument_key",
        symbol_value=initial_quote.instrument_key,
        quote=initial_quote,
        initial_price=initial_price,
        poll_interval=poll_interval,
        agents_count=len(agents),
        speed=request.speed,
        scenario_name=scenario.name,
    )


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
        "events": active_simulator.get_recent_events(limit=20),
        "order_flow": active_simulator.get_order_flow_summary(),
        "recent_orders": active_simulator.get_recent_orders(limit=20),
    }

    if "oracle" in state:
        update["oracle"] = state["oracle"]

    data_source = getattr(active_simulator, "data_source", None)
    if data_source:
        update["data_source"] = data_source

    return update


def _build_abides_update(*, state: dict, agent_metrics: dict, active_abides) -> dict:
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
        "speed": active_abides.speed_multiplier,
        "events": active_abides.get_recent_events(limit=20),
        "order_flow": active_abides.get_order_flow_summary(),
        "recent_orders": active_abides.get_recent_orders(limit=20),
    }

    if state.get("oracle"):
        update["oracle"] = state.get("oracle")

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
            _record_step_warnings(
                state=state,
                liquidity_prediction=liquidity_pred,
                large_order_detection=large_order_det,
            )

            agent_metrics = _agent_metrics_for(simulator.agents, simulator.current_price)

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

            agent_metrics = _agent_metrics_for(
                abides_simulator.agents.values(),
                state.get("mid_price") or state.get("price") or 0.0,
            )
            update = _build_abides_update(
                state=state,
                agent_metrics=agent_metrics,
                active_abides=abides_simulator,
            )

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
