"""Run a minimal ABIDES-style simulation."""

from __future__ import annotations

try:
    from _path_setup import add_backend_to_path
except ModuleNotFoundError:
    from backend.scripts._path_setup import add_backend_to_path

add_backend_to_path()

from src.abides.simulation import AbidesSimulation
from src.abides.agents.exchange import ExchangeAgent
from src.abides.agents.market_maker import MarketMakerAgent
from src.abides.agents.noise import NoiseAgent
from src.abides.agents.informed import InformedAgent
from src.market.oracle import OracleConfig
from src.market.latency_model import LatencyConfig, LatencyMode


def main() -> None:
    sim = AbidesSimulation(
        oracle_config=OracleConfig(r_bar=100.0, kappa=0.05, sigma_s=0.02, enabled=True),
        latency_config=LatencyConfig(mode=LatencyMode.CUBIC),
        speed_multiplier=2.0,
    )
    exchange = ExchangeAgent()
    sim.set_exchange(exchange)

    sim.register_agent(MarketMakerAgent("MM_1", wakeup_interval=0.5))
    sim.register_agent(NoiseAgent("NOISE_1", wakeup_interval=0.3, order_rate=0.8))
    sim.register_agent(NoiseAgent("NOISE_2", wakeup_interval=0.4, order_rate=0.6))
    sim.register_agent(InformedAgent("INF_1", wakeup_interval=0.7, mispricing_threshold=0.15))

    sim.run(duration_seconds=10.0)

    book = exchange.order_book
    print("ABIDES demo completed")
    print(f"Best bid: {book.best_bid} | Best ask: {book.best_ask} | Mid: {book.mid_price}")


if __name__ == "__main__":
    main()
