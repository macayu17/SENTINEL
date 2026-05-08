"""Shared training-time simulator factories for market-making policies."""

from __future__ import annotations

from .rl_env import MarketMakerEnv
from .simulator import MarketSimulator
from ..agents.hft_agent import HFTAgent
from ..agents.informed import InformedAgent
from ..agents.liquidity_trader import LiquidityTraderAgent
from ..agents.noise import NoiseAgent
from ..agents.retail import RetailAgent
from ..agents.rl_agent import RLAgent


def build_training_agents() -> list:
    """Construct a heterogeneous population for policy training."""
    return [
        RLAgent("RL_MM", initial_capital=100000.0),
        HFTAgent("HFT_1", position_limit=600),
        InformedAgent("INF_1", signal_probability=0.02, signal_accuracy=0.62),
        LiquidityTraderAgent("LIQ_1", start_probability=0.03),
        RetailAgent("RET_1"),
        NoiseAgent("Noise_1", order_rate=0.35),
        NoiseAgent("Noise_2", order_rate=0.45),
    ]


def create_training_simulator(
    initial_price: float = 100.0,
    duration_seconds: int = 1000,
) -> MarketSimulator:
    return MarketSimulator(
        agents=build_training_agents(),
        initial_price=initial_price,
        duration_seconds=duration_seconds,
    )


def create_market_maker_env(
    initial_price: float = 100.0,
    duration_seconds: int = 1000,
    rl_agent_id: str = "RL_MM",
) -> MarketMakerEnv:
    return MarketMakerEnv(
        simulator=create_training_simulator(
            initial_price=initial_price,
            duration_seconds=duration_seconds,
        ),
        rl_agent_id=rl_agent_id,
    )
