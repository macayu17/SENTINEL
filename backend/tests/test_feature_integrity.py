from pathlib import Path

from backend.src.agents.base_agent import BaseAgent
from backend.src.agents.informed import InformedAgent
from backend.src.agents.risk import AgentRiskProfile
from backend.src.market.latency_model import LatencyConfig, LatencyMode, LatencyModel
from backend.src.market.oracle import OracleConfig
from backend.src.market.order import Order, OrderSide, OrderType
from backend.src.market.simulator import MarketSimulator, create_sandbox_agents
from backend.src.prediction.large_order import LargeOrderDetector
from backend.src.prediction.liquidity_shock import LiquidityShockPredictor
from backend.src.api import main as api_main


class StaticAgent(BaseAgent):
    def __init__(self, agent_id: str, agent_type: str = "Retail") -> None:
        super().__init__(agent_id, agent_type, latency_seconds=0.25)
        self.risk_profile = AgentRiskProfile(max_inventory=1_000, base_order_size=10)

    def decide_action(self, market_state):
        return [Order(self.agent_id, OrderSide.BUY, OrderType.LIMIT, 99.99, 10)]


def _scheduled_order_delay(simulator: MarketSimulator, agent: BaseAgent) -> float:
    simulator.kernel.clear()
    simulator._request_agent_orders(agent)
    event = min(simulator.kernel.queue, key=lambda item: item.timestamp)
    return event.timestamp - simulator.current_time


def test_latency_mode_controls_exchange_arrival_delay():
    zero_agent = StaticAgent("ZERO")
    zero = MarketSimulator(
        [zero_agent],
        latency_config=LatencyConfig(mode=LatencyMode.ZERO),
        seed=7,
    )
    deterministic_agent = StaticAgent("FIXED")
    deterministic = MarketSimulator(
        [deterministic_agent],
        latency_config=LatencyConfig(mode=LatencyMode.DETERMINISTIC),
        seed=7,
    )

    assert _scheduled_order_delay(zero, zero_agent) == 0.0
    assert _scheduled_order_delay(deterministic, deterministic_agent) == 0.01


def test_cubic_latency_adds_seeded_bounded_congestion_jitter():
    first = LatencyModel(LatencyConfig(mode=LatencyMode.CUBIC))
    second = LatencyModel(LatencyConfig(mode=LatencyMode.CUBIC))
    first.reset(19)
    second.reset(19)

    samples = [first.get_latency("Retail") for _ in range(2_000)]
    repeated = [second.get_latency("Retail") for _ in range(2_000)]

    assert samples == repeated
    assert max(samples) - 0.01 > 0.01
    assert max(samples) <= 0.0600001


def test_oracle_state_reaches_agents_and_drives_informed_direction():
    simulator = MarketSimulator(
        [],
        oracle_config=OracleConfig(enabled=True, r_bar=101.0, sigma_s=0.0),
        seed=11,
    )
    state = simulator.get_market_state()

    assert state["oracle"]["fundamental_value"] == 101.0

    agent = InformedAgent("INF", signal_probability=1.0)
    orders = agent.decide_action({
        **state,
        "mid_price": 100.0,
        "current_price": 100.0,
        "spread": 0.02,
        "ask_depth": 5_000,
        "bid_depth": 5_000,
        "recent_price_change": -0.1,
        "recent_signed_volume": -5_000,
        "order_book_imbalance": -0.8,
    })

    assert orders
    assert orders[0].side == OrderSide.BUY


def test_simulator_reset_rewinds_seeded_oracle():
    simulator = MarketSimulator(
        [],
        oracle_config=OracleConfig(enabled=True, r_bar=100.0, sigma_s=0.2),
        seed=23,
    )
    first = simulator.oracle.advance()
    simulator.reset(seed=23)

    assert simulator.oracle.current_value == 100.0
    assert simulator.oracle.advance() == first


def _noise_trace(*, interleave_other_agent: bool) -> list[tuple]:
    agents = create_sandbox_agents(custom_agents={"Noise": 2}, seed=41)
    simulator = MarketSimulator(agents, seed=2718)
    target, other = agents
    target.order_rate = 1.0
    other.order_rate = 1.0
    state = simulator.get_market_state()
    trace = []
    for _ in range(6):
        if interleave_other_agent:
            other.decide_action(state)
        orders = target.decide_action(state)
        trace.append(tuple((order.side, order.order_type, order.price, order.quantity) for order in orders))
    return trace


def test_agent_random_stream_is_not_changed_by_another_agent():
    assert _noise_trace(interleave_other_agent=False) == _noise_trace(interleave_other_agent=True)


def test_clear_oracle_gap_drives_informed_direction_without_coin_flip():
    agent = InformedAgent("INF", signal_probability=1.0)
    agent.set_random_seed(2)

    orders = agent.decide_action({
        "current_time": 1.0,
        "mid_price": 100.0,
        "current_price": 100.0,
        "spread": 0.02,
        "ask_depth": 5_000,
        "bid_depth": 5_000,
        "volatility": 0.0,
        "oracle": {
            "fundamental_value": 102.0,
            "observation_noise": 0.005,
        },
    })

    assert orders
    assert orders[0].side == OrderSide.BUY


def test_informed_agent_waits_without_private_reference_value():
    agent = InformedAgent("INF", signal_probability=1.0)
    agent.set_random_seed(2)

    orders = agent.decide_action({
        "current_time": 1.0,
        "mid_price": 100.0,
        "current_price": 100.0,
        "spread": 0.02,
        "ask_depth": 5_000,
        "bid_depth": 5_000,
        "recent_price_change": 0.5,
        "recent_signed_volume": 5_000,
        "order_book_imbalance": 0.8,
        "volatility": 0.0,
    })

    assert orders == []
    assert agent._active_signal is None


def test_hidden_reference_process_advances_without_leaking_into_public_state():
    simulator = MarketSimulator(
        [],
        oracle_config=OracleConfig(enabled=True, r_bar=100.0, kappa=0.0, sigma_s=0.02),
        informed_oracle_access=False,
        seed=11,
    )
    initial_reference = simulator.oracle.current_value

    state = simulator.step()

    assert simulator.oracle.current_value != initial_reference
    assert "oracle" not in state


def test_reference_flow_moves_one_visible_level_toward_latent_value():
    simulator = MarketSimulator(
        [],
        initial_price=100.0,
        oracle_config=OracleConfig(enabled=True, r_bar=100.10, sigma_s=0.0),
        informed_oracle_access=False,
        seed=11,
    )
    initial_ask = simulator.order_book.best_ask

    assert simulator._apply_reference_flow() is True

    reference_trades = [
        trade for trade in simulator._all_trades
        if trade.taker_agent_id == "REFERENCE_FLOW"
    ]
    assert reference_trades
    assert {trade.price for trade in reference_trades} == {initial_ask}
    assert simulator.order_book.best_ask > initial_ask


def test_liquidity_diagnostic_learns_baseline_and_reports_observed_stress(tmp_path: Path):
    predictor = LiquidityShockPredictor(model_path=str(tmp_path / "missing.pkl"))
    normal_state = {
        "mid_price": 100.0,
        "spread": 0.02,
        "total_depth": 5_000,
        "volatility": 0.01,
        "recent_signed_volume": 50,
        "agents": {"MM": {"type": "MarketMaker", "inventory_ratio": 0.0}},
    }
    for _ in range(20):
        normal = predictor.predict(normal_state)

    stressed = predictor.predict({
        "mid_price": 100.0,
        "spread": 0.30,
        "total_depth": 200,
        "volatility": 0.10,
        "recent_signed_volume": 2_000,
        "agents": {"MM": {"type": "MarketMaker", "inventory_ratio": 0.95}},
    })

    assert normal["method"] == "adaptive_stress"
    assert normal["horizon_seconds"] == 0
    assert normal["warning_level"] == "safe"
    assert normal["stress_score"] < stressed["stress_score"]
    assert stressed["stress_score"] >= 0.6
    assert "probability" not in stressed
    assert stressed["warning_level"] in {"warning", "critical"}


def test_simulation_market_is_explicitly_nasdaq():
    simulator = MarketSimulator([], seed=7)

    state = simulator.get_market_state()

    assert state["venue"] == "NASDAQ"
    assert state["market"] == "NASDAQ"


def test_visible_liquidity_detector_flags_only_concentrated_book_levels():
    detector = LargeOrderDetector()
    balanced = {
        "bid_levels": [{"price": 99.99, "size": 500}, {"price": 99.98, "size": 450}],
        "ask_levels": [{"price": 100.01, "size": 500}, {"price": 100.02, "size": 450}],
        "total_depth": 1_900,
    }
    concentrated = {
        **balanced,
        "bid_levels": [{"price": 99.99, "size": 5_000}, {"price": 99.98, "size": 450}],
        "total_depth": 6_400,
    }

    assert detector.detect(balanced) is None
    result = detector.detect(concentrated)

    assert result is not None
    assert result["pattern"] == "large_level"
    assert result["side"] == "buy"
    assert result["estimated_size"] == 5_000
    assert result["source"] == "visible_order_book"
    assert result["depth_share"] == 0.7812


def test_match_rate_counts_matched_orders_not_trade_prints():
    simulator = MarketSimulator([], seed=3)
    simulator._process_order(
        Order("TAKER", OrderSide.BUY, OrderType.MARKET, 101.0, 10_000)
    )
    flow = simulator.get_order_flow_summary()

    assert flow["fills"] > 1
    assert flow["submitted"] == 1
    assert flow["match_rate"] == 100.0


def test_warning_timeline_records_transitions_instead_of_every_tick():
    previous = api_main._warning_timeline
    api_main._warning_timeline = []
    try:
        caution = {
            "probability": 0.25,
            "health_score": 75.0,
            "warning_level": "caution",
        }
        state = {"current_time": 1.0, "scenario": {"name": "normal"}}
        api_main._record_step_warnings(
            state=state,
            liquidity_prediction=caution,
            large_order_detection=None,
        )
        state["current_time"] = 2.0
        api_main._record_step_warnings(
            state=state,
            liquidity_prediction=caution,
            large_order_detection=None,
        )

        assert len(api_main._warning_timeline) == 1
    finally:
        api_main._warning_timeline = previous


def test_backend_exposes_only_sentinel_sim_workflow():
    root = Path(__file__).resolve().parents[2]
    api_source = (root / "backend" / "src" / "api" / "main.py").read_text(encoding="utf-8")
    requirements = (root / "backend" / "requirements.txt").read_text(encoding="utf-8")

    for removed_surface in (
        "/api/sandbox/abides",
        "/api/live-shadow",
        "/api/sandbox/stock",
        "RL_MM",
        "rl_policy",
    ):
        assert removed_surface.lower() not in api_source.lower()

    assert not any((root / "backend" / "src" / "abides").rglob("*.py"))

    for removed_path in (
        root / "backend" / "src" / "data" / "groww_provider.py",
        root / "backend" / "src" / "agents" / "rl_agent.py",
        root / "backend" / "src" / "agents" / "wash_trader.py",
        root / "backend" / "src" / "market" / "surveillance.py",
    ):
        assert not removed_path.exists()

    assert "growwapi" not in requirements.lower()
