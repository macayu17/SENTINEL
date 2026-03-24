"""FastAPI application — REST endpoints and WebSocket for SENTINEL."""

from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
import asyncio
import time

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
)
from ..utils.logger import get_logger
from ..utils.config import config

logger = get_logger("api")

# Global singletons
simulator: Optional[MarketSimulator] = None
liquidity_predictor = LiquidityShockPredictor()
large_order_detector = LargeOrderDetector()
signal_engine = SignalEngine()
manager = ConnectionManager()

# Stream task handle (simulation loop or live-shadow loop)
_stream_task: Optional[asyncio.Task] = None
_live_shadow_state: Optional[Dict[str, Any]] = None
_live_feed: Optional[LiveMarketFeed] = None
_mock_live_feed: Optional[MockLiveFeedAdapter] = None
_live_fallback_active: bool = False
_active_live_source: str = "simulation"
_last_live_feed_stale_state: Optional[bool] = None


def _normalize_mode(mode: str) -> str:
    normalized = mode.strip().upper()
    if normalized == "SANDBOX":
        return "SIMULATION"
    if normalized in {"SIMULATION", "LIVE_SHADOW"}:
        return normalized
    raise ValueError("Invalid mode")


def _rl_status_from_metrics(agent_metrics: Dict[str, Dict[str, Any]], mode: str) -> Dict[str, Any]:
    has_rl_agent = any(m.get("agent_type") == "RL_MM" for m in agent_metrics.values())
    if not has_rl_agent:
        return {"state": "idle"}
    if mode == "LIVE_SHADOW":
        return {"state": "evaluating"}
    return {"state": "training"}


def _phase_status() -> list[Dict[str, str]]:
    return [
        {"phase": "Phase 1", "status": "completed"},
        {"phase": "Phase 2", "status": "completed"},
        {"phase": "Phase 3", "status": "in-progress"},
        {"phase": "Phase 4", "status": "in-progress"},
    ]


def _signal_payload(
    *,
    mid_price: float,
    spread: float,
    order_book_imbalance: float,
    recent_price_movement: float,
    trade_flow: float,
    inventory: float,
) -> Dict[str, Any]:
    return signal_engine.predict(
        SignalInput(
            mid_price=mid_price,
            spread=spread,
            order_book_imbalance=order_book_imbalance,
            recent_price_movement=recent_price_movement,
            trade_flow=trade_flow,
            inventory=inventory,
        )
    )


def _build_live_feed_adapter() -> LiveMarketFeed:
    config.validate()
    provider = config.live_feed_provider.lower()
    if provider == "binance":
        return BinanceLiveFeedAdapter(
            symbol=config.live_feed_symbol,
            duration_seconds=config.simulation_duration,
            reconnect_base_delay=config.live_feed_reconnect_base,
            reconnect_max_delay=config.live_feed_reconnect_max,
        )
    if provider == "broker":
        return BrokerExchangeLiveFeedAdapter(
            symbol=config.live_feed_symbol,
            duration_seconds=config.simulation_duration,
            stream_mode=config.broker_stream_mode,
            ws_url=config.broker_ws_url,
            rest_url=config.broker_rest_url,
            auth=BrokerAuthConfig(
                api_key=config.broker_api_key,
                api_secret=config.broker_api_secret,
                access_token=config.broker_access_token,
                account_id=config.broker_account_id,
            ),
            poll_interval_seconds=config.live_feed_poll_interval_seconds,
            stale_after_seconds=config.live_feed_stale_after_seconds,
            reconnect_base_delay=config.live_feed_reconnect_base,
            reconnect_max_delay=config.live_feed_reconnect_max,
        )
    if provider == "nse":
        return NseLikeLiveFeedAdapter(
            symbol=config.live_feed_symbol,
            duration_seconds=config.simulation_duration,
            reconnect_base_delay=config.live_feed_reconnect_base,
            reconnect_max_delay=config.live_feed_reconnect_max,
        )
    if provider == "mock":
        return MockLiveFeedAdapter(
            initial_price=config.initial_price,
            duration_seconds=config.simulation_duration,
        )
    raise ValueError(f"Unsupported live feed provider: {provider}")


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
    global simulator

    try:
        normalized = _normalize_mode(request.mode)
    except ValueError:
        return {"error": "Invalid mode. Use SIMULATION or LIVE_SHADOW."}

    config.simulation_mode = normalized
    if simulator:
        simulator.mode = normalized

    return {"status": "mode_updated", "mode": normalized}


@app.post("/api/simulation/start")
async def start_simulation():
    global simulator, _stream_task, _live_shadow_state, _live_feed, _mock_live_feed
    global _live_fallback_active, _active_live_source, _last_live_feed_stale_state

    if _stream_task and not _stream_task.done():
        return {"status": "already_running", "mode": config.simulation_mode}

    mode = _normalize_mode(config.simulation_mode)
    config.simulation_mode = mode

    if mode == "SIMULATION":
        agents = (
            [MarketMakerAgent(f"MM_{i}") for i in range(3)]
            + [HFTAgent(f"HFT_{i}") for i in range(2)]
            + [InstitutionalAgent(f"INST_{i}") for i in range(2)]
            + [RetailAgent(f"RET_{i}") for i in range(10)]
            + [InformedAgent(f"INF_{i}") for i in range(3)]
            + [NoiseAgent(f"NOISE_{i}") for i in range(10)]
        )

        simulator = MarketSimulator(
            agents,
            initial_price=config.initial_price,
            duration_seconds=config.simulation_duration,
            mode=mode,
        )

        _stream_task = asyncio.create_task(_run_simulation_loop())
        return {
            "status": "started",
            "mode": mode,
            "agents": len(agents),
            "initial_price": config.initial_price,
        }

    simulator = None
    _live_shadow_state = None
    _live_fallback_active = False
    _active_live_source = "unknown"
    _last_live_feed_stale_state = None

    _mock_live_feed = MockLiveFeedAdapter(
        initial_price=config.initial_price,
        duration_seconds=config.simulation_duration,
    )
    await _mock_live_feed.start()

    try:
        _live_feed = _build_live_feed_adapter()
        await _live_feed.start()
        feed_health = _live_feed.health()
        _active_live_source = feed_health.source
        logger.info(
            f"LIVE_SHADOW using provider={config.live_feed_provider} symbol={config.live_feed_symbol}"
        )
    except Exception as exc:
        _live_feed = None
        _active_live_source = "mock"
        _live_fallback_active = True
        logger.warning(f"Live feed adapter startup failed, fallback to mock: {exc}")

    _stream_task = asyncio.create_task(_run_live_shadow_loop())
    return {
        "status": "started",
        "mode": mode,
        "source": _active_live_source,
        "fallback_active": _live_fallback_active,
    }


@app.post("/api/simulation/stop")
async def stop_simulation():
    global simulator, _stream_task, _live_feed, _mock_live_feed
    global _live_fallback_active, _active_live_source, _last_live_feed_stale_state

    if simulator:
        simulator.stop()
    if _stream_task:
        _stream_task.cancel()
        _stream_task = None

    if _live_feed:
        await _live_feed.stop()
        _live_feed = None
    if _mock_live_feed:
        await _mock_live_feed.stop()
        _mock_live_feed = None

    _live_fallback_active = False
    _active_live_source = "simulation"
    _last_live_feed_stale_state = None

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
    live_feed = {
        "connected": False,
        "source": "simulation",
        "provider": "simulation",
        "fallback_active": False,
        "last_update_ts": None,
        "last_update_wall_time": None,
        "stale": False,
        "latency_ms": None,
        "transport": None,
        "message": None,
    }
    if simulator is None:
        if _live_shadow_state is None:
            return {"error": "No active stream"}
        state = _live_shadow_state
        if _live_feed:
            h = _live_feed.health()
            live_feed = {
                "connected": h.connected,
                "source": _active_live_source,
                "provider": h.provider,
                "fallback_active": _live_fallback_active,
                "last_update_ts": h.last_update_ts,
                "last_update_wall_time": h.last_update_wall_time,
                "stale": h.stale,
                "latency_ms": h.latency_ms,
                "transport": h.transport,
                "message": h.message,
            }
        if _live_fallback_active:
            live_feed["source"] = "mock"
    else:
        state = simulator.get_market_state()

    return {
        "price": state["current_price"],
        "mid_price": state["mid_price"],
        "spread": state["spread"],
        "best_bid": state["best_bid"],
        "best_ask": state["best_ask"],
        "depth": state["total_depth"],
        "order_book": {
            "bids": state["order_book_levels"]["bids"],
            "asks": state["order_book_levels"]["asks"],
        },
        "order_book_imbalance": state["order_book_imbalance"],
        "volatility": state["volatility"],
        "step": state["step"],
        "mode": config.simulation_mode,
        "live_feed": live_feed,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


async def _run_simulation_loop():
    """Run simulator stream and broadcast dashboard.v1 updates."""
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

            agent_metrics = {}
            for agent in simulator.agents:
                m = agent.get_metrics(simulator.current_price)
                agent_metrics[agent.agent_id] = {
                    "total_pnl": m["total_pnl"],
                    "realized_pnl": m["realized_pnl"],
                    "unrealized_pnl": m["unrealized_pnl"],
                    "return_pct": m["return_pct"],
                    "sharpe_ratio": m["sharpe_ratio"],
                    "agent_type": m["agent_type"],
                    "position": m["position"],
                    "num_trades": m["num_trades"],
                }

            activity = simulator.get_recent_activity(limit=20)
            recent_orders = activity.get("orders", [])
            recent_trades = activity.get("trades", [])
            recent_events = activity.get("events", [])
            agent_actions = activity.get("agent_actions", {})

            total_inventory = sum(m["position"] for m in agent_metrics.values())
            total_realized = sum(m.get("realized_pnl", 0.0) for m in agent_metrics.values())
            total_unrealized = sum(m.get("unrealized_pnl", 0.0) for m in agent_metrics.values())
            total_reward = sum(m.get("total_pnl", 0.0) for m in agent_metrics.values())

            fills = len(recent_trades)
            submitted = len(recent_orders)
            cancelled = sum(1 for o in recent_orders if o.get("status") == "Cancelled")
            match_rate = (fills / submitted * 100.0) if submitted > 0 else 0.0

            trade_flow = state.get("recent_signed_volume", 0.0) / max(1.0, state.get("total_depth", 1.0))
            signal = _signal_payload(
                mid_price=state["mid_price"],
                spread=state["spread"],
                order_book_imbalance=state["order_book_imbalance"],
                recent_price_movement=state.get("recent_price_change", 0.0),
                trade_flow=trade_flow,
                inventory=total_inventory,
            )

            update = {
                "type": "market_update",
                "data_contract_version": "dashboard.v1",
                "timestamp": state["current_time"],
                "price": state["current_price"],
                "mid_price": state["mid_price"],
                "best_bid": state["best_bid"],
                "best_ask": state["best_ask"],
                "spread": state["spread"],
                "depth": state["total_depth"],
                "order_book_imbalance": state["order_book_imbalance"],
                "order_book": {
                    "bids": state["order_book_levels"]["bids"][:10],
                    "asks": state["order_book_levels"]["asks"][:10],
                },
                "liquidity_prediction": liquidity_pred,
                "large_order_detection": large_order_det,
                "agent_metrics": agent_metrics,
                "inventory": total_inventory,
                "realized_pnl": total_realized,
                "unrealized_pnl": total_unrealized,
                "cumulative_reward": total_reward,
                "recent_orders": recent_orders,
                "recent_trades": recent_trades,
                "recent_events": recent_events,
                "agent_actions": agent_actions,
                "execution_summary": {
                    "submitted": submitted,
                    "fills": fills,
                    "cancelled": cancelled,
                    "match_rate": round(match_rate, 2),
                },
                "rl_status": _rl_status_from_metrics(agent_metrics, config.simulation_mode),
                "phase_status": _phase_status(),
                "simulation_time": state["current_time"],
                "time_to_close": state["time_to_close"],
                "step": state["step"],
                "volatility": state["volatility"],
                "mode": config.simulation_mode,
                "signal": signal,
                "live_feed": {
                    "connected": False,
                    "source": "simulation",
                    "provider": "simulation",
                    "fallback_active": False,
                    "last_update_ts": None,
                    "last_update_wall_time": None,
                    "stale": False,
                    "latency_ms": None,
                    "transport": "simulation",
                    "message": "simulation_mode",
                },
            }

            if manager.client_count > 0:
                await manager.broadcast(update)

            await asyncio.sleep(0.1)

    except asyncio.CancelledError:
        logger.info("Simulation loop cancelled")
    except Exception as exc:
        logger.error(f"Simulation loop error: {exc}")
    finally:
        if simulator:
            simulator.running = False
        logger.info("Simulation loop ended")


async def _run_live_shadow_loop():
    """Run LIVE_SHADOW stream with real adapter and fallback mock feed."""
    global _live_shadow_state, _live_fallback_active, _active_live_source, _last_live_feed_stale_state

    logger.info("Live shadow loop started")
    last_feed_connected: Optional[bool] = None
    last_fallback_state: Optional[bool] = None

    try:
        while True:
            state = None
            source = "mock"
            feed_connected = False
            provider = config.live_feed_provider
            last_update_ts = None
            last_update_wall_time = None
            feed_stale = False
            feed_latency_ms = None
            feed_transport = None
            feed_message = ""

            if _live_feed:
                feed_health = _live_feed.health()
                feed_connected = feed_health.connected
                provider = feed_health.provider
                last_update_ts = feed_health.last_update_ts
                last_update_wall_time = feed_health.last_update_wall_time
                feed_stale = feed_health.stale
                feed_latency_ms = feed_health.latency_ms
                feed_transport = feed_health.transport
                feed_message = feed_health.message
                if _last_live_feed_stale_state is None or _last_live_feed_stale_state != feed_stale:
                    if feed_stale:
                        logger.warning("Live feed marked stale; fallback path may activate")
                    else:
                        logger.info("Live feed freshness restored")
                    _last_live_feed_stale_state = feed_stale
                if feed_health.connected:
                    maybe = _live_feed.latest_state()
                    if maybe is not None and not feed_stale:
                        state = maybe.to_dict()
                        source = feed_health.source
                        _live_fallback_active = False
                        _active_live_source = source

            if state is None and _mock_live_feed:
                maybe = _mock_live_feed.latest_state()
                if maybe is not None:
                    state = maybe.to_dict()
                    source = "mock"
                    _live_fallback_active = provider != "mock"
                    _active_live_source = "mock"
                    if _mock_live_feed.health().last_update_ts is not None:
                        last_update_ts = _mock_live_feed.health().last_update_ts
                    last_update_wall_time = time.time()
                    feed_latency_ms = 0.0
                    feed_stale = False
                    feed_transport = "fallback"
                    if provider != "mock":
                        feed_message = "real_feed_unavailable_using_mock_fallback"

            if state is None:
                await asyncio.sleep(0.25)
                continue

            _live_shadow_state = state

            if last_feed_connected is None or last_feed_connected != feed_connected:
                if feed_connected:
                    logger.info("Live market connected")
                else:
                    logger.warning("Live market disconnected, using mock fallback")
                last_feed_connected = feed_connected

            if last_fallback_state is None or last_fallback_state != _live_fallback_active:
                if _live_fallback_active:
                    logger.warning(
                        f"Fallback activated: provider={provider} source={source} message={feed_message}"
                    )
                else:
                    logger.info(f"Fallback cleared: provider={provider} source={source}")
                last_fallback_state = _live_fallback_active

            liquidity_pred = liquidity_predictor.predict(state)

            trade_flow = state.get("recent_signed_volume", 0.0)
            signal = _signal_payload(
                mid_price=state["mid_price"],
                spread=state["spread"],
                order_book_imbalance=state["order_book_imbalance"],
                recent_price_movement=state.get("recent_price_change", 0.0),
                trade_flow=trade_flow,
                inventory=0.0,
            )

            recent_orders = state.get("recent_orders", [])
            recent_trades = state.get("recent_trades", [])
            recent_events = state.get("recent_events", [])

            submitted = len(recent_orders)
            fills = len(recent_trades)
            cancelled = sum(1 for order in recent_orders if order.get("status") == "Cancelled")
            match_rate = (fills / submitted * 100.0) if submitted > 0 else 0.0

            update = {
                "type": "market_update",
                "data_contract_version": "dashboard.v1",
                "timestamp": state["current_time"],
                "price": state["current_price"],
                "mid_price": state["mid_price"],
                "best_bid": state["best_bid"],
                "best_ask": state["best_ask"],
                "spread": state["spread"],
                "depth": state["total_depth"],
                "order_book_imbalance": state["order_book_imbalance"],
                "order_book": {
                    "bids": state["order_book_levels"]["bids"][:10],
                    "asks": state["order_book_levels"]["asks"][:10],
                },
                "liquidity_prediction": liquidity_pred,
                "large_order_detection": None,
                "agent_metrics": {},
                "inventory": 0,
                "realized_pnl": 0,
                "unrealized_pnl": 0,
                "cumulative_reward": 0,
                "recent_orders": recent_orders,
                "recent_trades": recent_trades,
                "recent_events": recent_events,
                "agent_actions": {"LIVE_FEED": "Ingesting real-market ticks"},
                "execution_summary": {
                    "submitted": submitted,
                    "fills": fills,
                    "cancelled": cancelled,
                    "match_rate": round(match_rate, 2),
                },
                "rl_status": {"state": "evaluating"},
                "phase_status": _phase_status(),
                "simulation_time": state["current_time"],
                "time_to_close": state["time_to_close"],
                "step": state["step"],
                "volatility": state["volatility"],
                "mode": "LIVE_SHADOW",
                "signal": signal,
                "live_feed": {
                    "connected": feed_connected,
                    "source": source,
                    "provider": provider,
                    "fallback_active": _live_fallback_active,
                    "last_update_ts": last_update_ts,
                    "last_update_wall_time": last_update_wall_time,
                    "stale": feed_stale,
                    "latency_ms": feed_latency_ms,
                    "transport": feed_transport,
                    "message": feed_message,
                },
            }

            if manager.client_count > 0:
                await manager.broadcast(update)

            await asyncio.sleep(0.25)

    except asyncio.CancelledError:
        logger.info("Live shadow loop cancelled")
    except Exception as exc:
        logger.error(f"Live shadow loop error: {exc}")
    finally:
        logger.info("Live shadow loop ended")
