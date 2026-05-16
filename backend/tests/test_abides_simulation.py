"""Minimal tests for ABIDES-style simulation."""

from src.abides.simulation import AbidesSimulation
from src.abides.agents.exchange import ExchangeAgent
from src.abides.agents.market_maker import MarketMakerAgent
from src.abides.agents.noise import NoiseAgent
from src.abides.agents.informed import InformedAgent
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
