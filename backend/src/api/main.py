"""FastAPI application — REST endpoints and WebSocket for SENTINEL."""

from contextlib import asynccontextmanager
from typing import Optional
import asyncio

from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .websocket import ConnectionManager
from ..market.simulator import MarketSimulator
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
from ..prediction.liquidity_shock import LiquidityShockPredictor
from ..prediction.large_order import LargeOrderDetector
from ..prediction.signal_engine import SignalEngine, SignalInput
from ..data.live_feed import (
    LiveMarketFeed,
    BinanceLiveFeedAdapter,
    BrokerExchangeLiveFeedAdapter,
    BrokerAuthConfig,
    MockLiveFeedAdapter,
    NseLikeLiveFeedAdapter,
    ScraperLiveFeedAdapter,
)
from ..utils.logger import get_logger
from ..utils.config import config

logger = get_logger("api")

# Global singletons
simulator: Optional[MarketSimulator] = None
liquidity_predictor = LiquidityShockPredictor()
large_order_detector = LargeOrderDetector()

# Signal engine with optional trained model
_model_path = Path(__file__).parent.parent.parent / "models" / "signal_model.pkl"
signal_engine: Optional[SignalEngine] = None

def _initialize_signal_engine() -> SignalEngine:
    """Initialize signal engine with trained model if available."""
    global signal_engine
    if signal_engine is None:
        signal_engine = SignalEngine(model_path=_model_path if _model_path.exists() else None)
    return signal_engine

manager = ConnectionManager()

# Simulation task handle
_sim_task: Optional[asyncio.Task] = None


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


@app.get("/api/health")
async def health_check():
    feed_health = _live_feed.health() if _live_feed else None
    return {
        "status": "healthy",
        "stream_active": _stream_task is not None and not _stream_task.done(),
        "simulation_active": simulator is not None and simulator.running,
        "connected_clients": manager.client_count,
        "mode": config.simulation_mode,
        "live_feed_connected": feed_health.connected if feed_health else False,
        "live_feed_source": feed_health.source if feed_health else None,
        "live_feed_provider": feed_health.provider if feed_health else config.live_feed_provider,
        "live_feed_last_update_ts": feed_health.last_update_ts if feed_health else None,
        "live_feed_last_update_wall_time": feed_health.last_update_wall_time if feed_health else None,
        "live_feed_fallback_active": _live_fallback_active,
        "live_feed_stale": feed_health.stale if feed_health else False,
        "live_feed_latency_ms": feed_health.latency_ms if feed_health else None,
        "live_feed_transport": feed_health.transport if feed_health else None,
        "live_feed_message": feed_health.message if feed_health else None,
    }


class ModeRequest(BaseModel):
    mode: str

@app.post("/api/simulation/mode")
async def set_simulation_mode(request: ModeRequest):
    if request.mode not in ["SANDBOX", "LIVE_SHADOW"]:
        return {"error": "Invalid mode"}
    
    config.simulation_mode = request.mode
    if simulator:
        simulator.mode = request.mode
        
    return {"status": "mode_updated", "mode": request.mode}


@app.post("/api/simulation/start")
async def start_simulation():
    global simulator, _sim_task

    if simulator and simulator.running:
        return {"status": "already_running", "step": simulator.step_count}

    # Create full agent set
    agents = (
        [MarketMakerAgent(f"MM_{i}") for i in range(3)]
        + [HFTAgent(f"HFT_{i}") for i in range(2)]
        + [InstitutionalAgent(f"INST_{i}") for i in range(2)]
        + [RetailAgent(f"RET_{i}") for i in range(10)]
        + [InformedAgent(f"INF_{i}") for i in range(3)]
        + [NoiseAgent(f"NOISE_{i}") for i in range(10)]
        + [MomentumAgent(f"MOM_{i}") for i in range(2)]
        + [MeanReversionAgent(f"MR_{i}") for i in range(2)]
        + [SpoofingAgent(f"SPOOF_0")]
        + [SentimentAgent(f"SENT_{i}") for i in range(5)]
    )

    simulator = MarketSimulator(
        agents,
        initial_price=config.initial_price,
        duration_seconds=config.simulation_duration,
        mode=config.simulation_mode,
    )

    # Run simulation in background task
    _sim_task = asyncio.create_task(_run_simulation_loop())

    return {
        "status": "started",
        "agents": len(agents),
        "initial_price": config.initial_price,
    }


@app.post("/api/simulation/stop")
async def stop_simulation():
    global simulator, _sim_task

    if simulator:
        simulator.stop()
    if _sim_task:
        _sim_task.cancel()
        _sim_task = None

    return {"status": "stopped"}


@app.get("/api/prediction/liquidity")
async def get_liquidity_prediction():
    if simulator is None:
        return {"error": "No active simulation"}
    state = simulator.get_market_state()
    return liquidity_predictor.predict(state)


@app.get("/api/prediction/large-order")
async def get_large_order_detection():
    if simulator is None:
        return {"error": "No active simulation"}
    state = simulator.get_market_state()
    detection = large_order_detector.detect(state)
    return detection or {"pattern": None, "message": "No large orders detected"}


@app.get("/api/agents/metrics")
async def get_agent_metrics():
    if simulator is None:
        return {"error": "No active simulation"}
    metrics = {}
    for agent in simulator.agents:
        metrics[agent.agent_id] = agent.get_metrics(simulator.current_price)
    return metrics


@app.get("/api/market/snapshot")
async def get_market_snapshot():
    if simulator is None:
        return {"error": "No active simulation"}
    state = simulator.get_market_state()
    return {
        "price": state["current_price"],
        "mid_price": state["mid_price"],
        "spread": state["spread"],
        "best_bid": state["best_bid"],
        "best_ask": state["best_ask"],
        "depth": state["total_depth"],
        "order_book": {
            "bids": state["bid_depth"],
            "asks": state["ask_depth"],
        },
        "volatility": state["volatility"],
        "step": state["step"],
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


async def _run_simulation_loop():
    """Run the simulation and broadcast updates via WebSocket."""
    global simulator

    if simulator is None:
        return

    simulator.running = True
    logger.info("Simulation loop started")

    try:
        while simulator.running and simulator.current_time < simulator.duration_seconds:
            # Run a step
            state = simulator.step()

            # Get predictions
            liquidity_pred = liquidity_predictor.predict(state)
            large_order_det = large_order_detector.detect(state)

            # Get agent metrics
            agent_metrics = {}
            for agent in simulator.agents:
                m = agent.get_metrics(simulator.current_price)
                agent_metrics[agent.agent_id] = {
                    "total_pnl": m["total_pnl"],
                    "sharpe_ratio": m["sharpe_ratio"],
                    "agent_type": m["agent_type"],
                    "position": m["position"],
                    "num_trades": m["num_trades"],
                }

            # Build the update message
            update = {
                "type": "market_update",
                "timestamp": state["current_time"],
                "price": state["current_price"],
                "spread": state["spread"],
                "depth": state["total_depth"],
                "order_book": {
                    "bids": state["bid_depth"][:10],
                    "asks": state["ask_depth"][:10],
                },
                "liquidity_prediction": liquidity_pred,
                "large_order_detection": large_order_det,
                "agent_metrics": agent_metrics,
                "step": state["step"],
                "volatility": state["volatility"],
                "mode": simulator.mode,
            }

            # Broadcast to all connected clients
            if manager.client_count > 0:
                await manager.broadcast(update)

            # ~10 Hz: sleep 100ms between steps
            await asyncio.sleep(0.1)

    except asyncio.CancelledError:
        logger.info("Simulation loop cancelled")
    except Exception as e:
        logger.error(f"Simulation loop error: {e}")
    finally:
        if simulator:
            simulator.running = False
        logger.info("Simulation loop ended")
