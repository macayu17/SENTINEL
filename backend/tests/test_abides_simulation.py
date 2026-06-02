"""Minimal tests for ABIDES-style simulation."""

from src.abides.simulation import AbidesSimulation
from src.abides.messages import OrderMessage
from src.abides.order_book import AbidesOrderBook
from src.abides.agents.base import Agent
from src.abides.agents.exchange import ExchangeAgent
from src.abides.agents.market_maker import MarketMakerAgent
from src.abides.agents.noise import NoiseAgent
from src.abides.agents.informed import InformedAgent
from src.market.order import OrderSide, OrderType
from src.market.oracle import OracleConfig


def test_abides_simulation_runs():
    sim = AbidesSimulation(oracle_config=OracleConfig(enabled=True))
    exchange = ExchangeAgent(initial_price=125.0)
    sim.set_exchange(exchange)

    sim.register_agent(MarketMakerAgent("MM_1", wakeup_interval=0.5))
    sim.register_agent(NoiseAgent("NOISE_1", wakeup_interval=0.2, order_rate=1.0))
    sim.register_agent(InformedAgent("INF_1", wakeup_interval=0.6, mispricing_threshold=0.05))

    assert sim.agents["MM_1"].last_mid == 125.0

    sim.run(duration_seconds=2.0)

    assert exchange.order_book.mid_price is not None or exchange.last_price > 0


def test_abides_agent_metrics_count_fills():
    sim = AbidesSimulation(oracle_config=OracleConfig(enabled=False))
    exchange = ExchangeAgent(initial_price=100.0)
    sim.set_exchange(exchange)

    sim.register_agent(MarketMakerAgent("MM_1", wakeup_interval=0.5))
    sim.register_agent(NoiseAgent("NOISE_1", wakeup_interval=0.2, order_rate=1.0))

    sim.run(duration_seconds=4.0)
    mark_price = exchange.order_book.mid_price or exchange.last_price
    metrics = [agent.get_metrics(mark_price) for agent in sim.agents.values()]

    assert any(metric["num_trades"] > 0 for metric in metrics)


def test_abides_order_book_depth_views_share_same_depth_snapshot():
    book = AbidesOrderBook()

    book.add_order("BUYER", OrderSide.BUY, OrderType.LIMIT, 99.5, 10)
    book.add_order("SELLER", OrderSide.SELL, OrderType.LIMIT, 100.5, 15)

    depth = book.get_depth(levels=10)

    assert book.get_levels(levels=10) == (depth["bids"], depth["asks"])
    assert book.bid_levels == depth["bids"]
    assert book.ask_levels == depth["asks"]
    assert book.get_total_depth(levels=10) == 25


def test_abides_export_snapshot_preserves_trace_and_order_flow_shape():
    sim = AbidesSimulation(oracle_config=OracleConfig(enabled=False))
    exchange = ExchangeAgent(initial_price=100.0)
    sim.set_exchange(exchange)
    sim.register_agent(Agent("BUYER", agent_type="TestBuyer"))
    sim.register_agent(Agent("SELLER", agent_type="TestSeller"))

    sim._dispatch_message(
        OrderMessage("SELLER", OrderSide.SELL, OrderType.LIMIT, 100.0, 25)
    )
    sim.kernel.run_until(1.0)
    sim._dispatch_message(
        OrderMessage("BUYER", OrderSide.BUY, OrderType.MARKET, 100.0, 25)
    )
    sim.kernel.run_until(2.0)

    summary = sim.get_order_flow_summary()
    events = sim.get_recent_events(limit=10)
    recent_orders = sim.get_recent_orders(limit=10)
    snapshot = sim.get_export_snapshot([{"warning_level": "safe"}])

    assert summary["submitted"] == 2
    assert summary["fills"] == 1
    assert summary["buy_volume"] == 25
    assert summary["sell_volume"] == 0
    assert events[0]["type"] == "fill"
    assert recent_orders[0]["status"] == "filled"
    assert snapshot["run_config"]["engine"] == "ABIDES"
    assert snapshot["order_flow"]["summary"] == summary
    assert snapshot["order_flow"]["trades"] == [
        {
            "price": 100.0,
            "quantity": 25,
            "buyer_agent_id": "BUYER",
            "seller_agent_id": "SELLER",
        }
    ]
    assert snapshot["events"][0]["type"] == "fill"
    assert snapshot["recent_orders"][0]["status"] == "filled"
    assert snapshot["warning_timeline"] == [{"warning_level": "safe"}]
