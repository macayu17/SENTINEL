"""Shared observation extraction for RL market-making policies."""

from typing import Optional

import numpy as np

from .simulator import MarketSimulator
from ..agents.base_agent import BaseAgent


def _get_agent(simulator: MarketSimulator, rl_agent_id: str) -> Optional[BaseAgent]:
    return simulator.get_agent(rl_agent_id)


def extract_market_maker_observation(
    simulator: MarketSimulator,
    rl_agent_id: str = "RL_MM",
    state: Optional[dict] = None,
    agent: Optional[BaseAgent] = None,
) -> np.ndarray:
    """Build the normalized 13-feature observation used by the PPO policy."""
    if state is None:
        state = simulator.get_market_state()

    mid_price = state["mid_price"]
    ref_px = 100.0 if mid_price == 0 else mid_price

    best_bid = (state["best_bid"] - ref_px) / ref_px if state["best_bid"] else 0.0
    best_ask = (state["best_ask"] - ref_px) / ref_px if state["best_ask"] else 0.0
    spread = state["spread"] / ref_px
    mid = (mid_price - 100.0) / 100.0

    b_depth, a_depth = state["bid_depth"], state["ask_depth"]
    imbalance = (b_depth - a_depth) / max(b_depth + a_depth, 1)

    if agent is None:
        agent = _get_agent(simulator, rl_agent_id)
    inventory = agent.position / 500.0 if agent else 0.0
    realized = (agent.realized_pnl / max(1.0, agent.initial_capital)) if agent else 0.0
    unrealized = (
        agent.get_unrealized_pnl(mid_price) / max(1.0, agent.initial_capital)
        if agent
        else 0.0
    )

    vol = state["volatility"]
    recent_px_chg = state.get("recent_price_change", 0.0)
    signed_vol = state.get("recent_signed_volume", 0.0) / 1000.0
    fill_rate = state.get("fill_rate", 0.0) / 10.0
    time = state["time_to_close"] / max(float(simulator.duration_seconds), 1.0)

    observation = np.empty(13, dtype=np.float32)
    observation[:] = (
        best_bid,
        best_ask,
        spread,
        mid,
        imbalance,
        recent_px_chg,
        signed_vol,
        inventory,
        realized,
        unrealized,
        vol,
        fill_rate,
        time,
    )
    return observation
