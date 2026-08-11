"""FastAPI application — REST endpoints and WebSocket for SENTINEL."""

from contextlib import asynccontextmanager
from math import sqrt
from typing import Iterable, Optional
import asyncio
import secrets

from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .websocket import ConnectionManager
from ..market.simulator import MarketSimulator, get_sandbox_presets, create_sandbox_agents
from ..market.oracle import OracleConfig
from ..market.latency_model import LatencyConfig, LatencyMode
from ..market.scenario import get_scenario_config, list_scenarios
from ..prediction.liquidity_shock import LiquidityShockPredictor
from ..prediction.large_order import LargeOrderDetector
from ..utils.logger import get_logger
from ..utils.config import config

logger = get_logger("api")

# Global singletons
simulator: Optional[MarketSimulator] = None
liquidity_predictor = LiquidityShockPredictor()
large_order_detector = LargeOrderDetector()
manager = ConnectionManager()

# Simulation task handle
_sim_task: Optional[asyncio.Task] = None
_warning_timeline: list[dict] = []
_warning_states: dict[str, tuple] = {}

LATENCY_MODES = {
    "zero": LatencyMode.ZERO,
    "deterministic": LatencyMode.DETERMINISTIC,
    "cubic": LatencyMode.CUBIC,
}

AGENT_METRIC_FIELDS = (
    "total_pnl",
    "realized_pnl",
    "unrealized_pnl",
    "halted",
    "agent_type",
    "position",
    "num_trades",
)


def _clamp_simulation_speed(speed: float) -> float:
    return max(0.1, min(20.0, float(speed)))


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
    simulation_active = simulator is not None and simulator.running
    return {
        "status": "healthy",
        "simulation_active": simulation_active,
        "connected_clients": manager.client_count,
        "engine": "SENTINEL",
    }


def _latency_config(latency_mode: str) -> LatencyConfig:
    return LatencyConfig(mode=LATENCY_MODES.get(latency_mode, LatencyMode.DETERMINISTIC))


def _stop_native_simulation() -> None:
    global _sim_task
    if simulator and simulator.running:
        simulator.stop()
    if _sim_task:
        _sim_task.cancel()
        _sim_task = None


def _prepare_simulator_replacement() -> None:
    _stop_native_simulation()
    liquidity_predictor.reset()
    large_order_detector.reset()


def _record_warning_event(event: dict) -> None:
    _warning_timeline.append(event)
    if len(_warning_timeline) > 500:
        del _warning_timeline[:-500]


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

    liquidity_level = liquidity_prediction.get("warning_level") if liquidity_prediction else None
    if liquidity_level not in {None, "safe"}:
        signature = (liquidity_level, scenario_name)
        if _warning_states.get("liquidity_stress") != signature:
            _record_warning_event({
            "timestamp": timestamp,
            "detector": "liquidity_stress",
            "warning_level": liquidity_level,
            "probability": liquidity_prediction.get("probability"),
            "stress_score": liquidity_prediction.get("stress_score"),
            "health_score": liquidity_prediction.get("health_score"),
            "scenario": scenario_name,
            })
            _warning_states["liquidity_stress"] = signature
    else:
        _warning_states.pop("liquidity_stress", None)

    if large_order_detection:
        signature = (
            large_order_detection.get("side"),
            large_order_detection.get("price"),
            large_order_detection.get("estimated_size"),
        )
        if _warning_states.get("visible_liquidity") != signature:
            _record_warning_event({
            "timestamp": timestamp,
            "detector": "visible_liquidity",
            "pattern": large_order_detection.get("pattern"),
            "side": large_order_detection.get("side"),
            "confidence": large_order_detection.get("confidence"),
            "estimated_size": large_order_detection.get("estimated_size"),
            "scenario": scenario_name,
            })
            _warning_states["visible_liquidity"] = signature
    else:
        _warning_states.pop("visible_liquidity", None)


@app.post("/api/simulation/stop")
async def stop_simulation():
    global simulator, _sim_task, _warning_timeline, _warning_states

    _stop_native_simulation()

    liquidity_predictor.reset()
    large_order_detector.reset()
    _warning_timeline = []
    _warning_states = {}
    return {"status": "stopped"}


@app.get("/api/simulation/export")
async def export_simulation_run():
    if simulator is not None:
        return simulator.get_export_snapshot(_warning_timeline)
    raise HTTPException(status_code=409, detail="No active simulation")


# ── Sandbox Endpoints ──────────────────────────────────────────────────────


@app.get("/api/sandbox/presets")
async def list_sandbox_presets():
    return get_sandbox_presets()


@app.get("/api/sandbox/scenarios")
async def list_sandbox_scenarios():
    return {"scenarios": list_scenarios()}


class SandboxCreateRequest(BaseModel):
    preset: str = "balanced"
    initial_price: float = 100.0
    oracle_enabled: bool = False
    latency_mode: str = "deterministic"
    speed: float = 1.0
    scenario: str = "normal"
    seed: Optional[int] = None


@app.post("/api/sandbox/create")
async def create_sandbox(request: SandboxCreateRequest):
    global simulator, _sim_task

    _prepare_simulator_replacement()

    scenario = get_scenario_config(request.scenario)
    run_seed = request.seed if request.seed is not None else secrets.randbits(32)
    run_speed = _clamp_simulation_speed(request.speed)
    agents = create_sandbox_agents(
        request.preset,
        scenario=scenario,
        seed=run_seed,
    )

    base_sigma = (
        request.initial_price
        * 0.30
        / sqrt(252 * 390 * 60)
    )
    oracle_cfg = OracleConfig(
        r_bar=request.initial_price,
        kappa=0.001,
        sigma_s=base_sigma * scenario.oracle_sigma_multiplier,
        enabled=True,
    )
    latency_cfg = _latency_config(request.latency_mode)

    simulator = MarketSimulator(
        agents, initial_price=request.initial_price,
        duration_seconds=config.simulation_duration,
        oracle_config=oracle_cfg, latency_config=latency_cfg, speed_multiplier=run_speed,
        scenario=scenario.name,
        informed_oracle_access=request.oracle_enabled,
        seed=run_seed,
    )
    _sim_task = asyncio.create_task(_run_simulation_loop())
    return {"status": "started", "preset": request.preset, "agents": len(agents),
            "oracle_enabled": request.oracle_enabled, "speed": run_speed,
            "scenario": scenario.name, "seed": run_seed}


class SpeedRequest(BaseModel):
    speed: float


@app.put("/api/sandbox/speed")
async def set_sandbox_speed(request: SpeedRequest):
    if simulator is None:
        return {"error": "No active simulation"}
    simulator.speed_multiplier = _clamp_simulation_speed(request.speed)
    return {"speed": simulator.speed_multiplier}


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
        "speed": getattr(active_simulator, "speed_multiplier", 1.0),
        "session_phase": state["session_phase"],
        "activity_multiplier": state["activity_multiplier"],
        "scenario": state["scenario"],
        "venue": state["venue"],
        "market": state["market"],
        "latency_mode": active_simulator.latency_model.describe()["mode"],
        "events": active_simulator.get_recent_events(limit=20),
        "order_flow": active_simulator.get_order_flow_summary(),
        "recent_orders": active_simulator.get_recent_orders(limit=20),
    }

    if "oracle" in state:
        update["oracle"] = state["oracle"]

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

            sleep_time = 0.1 / _clamp_simulation_speed(simulator.speed_multiplier)
            await asyncio.sleep(sleep_time)

    except asyncio.CancelledError:
        logger.info("Simulation loop cancelled")
    except Exception as e:
        logger.error(f"Simulation loop error: {e}")
    finally:
        if simulator:
            simulator.running = False
        logger.info("Simulation loop ended")
