"""Gymnasium environment for training Reinforcement Learning agents in the limit order book."""

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Dict, Tuple
from .simulator import MarketSimulator
from .rl_features import extract_market_maker_observation
from ..agents.rl_agent import RLAgent

class MarketMakerEnv(gym.Env):
    """
    RL Environment where the agent acts as a Market Maker.
    Actions: Continuous[spread, skew, size]
      - spread (-1 to 1): Distance between quotes.
      - skew (-1 to 1): Inventory bias (offsets quotes).
      - size (-1 to 1): Quantity of shares to offer.
    Observations: Vector of 13 normalized market and agent variables.
    """
    
    def __init__(self, simulator: MarketSimulator, rl_agent_id: str = "RL_MM"):
        super(MarketMakerEnv, self).__init__()
        self.simulator = simulator
        self.rl_agent_id = rl_agent_id
        
        # Action space: [spread, skew, size] between -1 and 1
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(3,), dtype=np.float32)
        
        # Observations: [best_bid, best_ask, spread, mid, imbalance, recent_px_chg,
        # signed_vol, inventory, realized_pnl, unrealized_pnl, vol, fill_rate, time]
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(13,), dtype=np.float32)
        
        # Tracking states for reward shaping
        self.last_total_pnl = 0.0
        self.last_realized_pnl = 0.0
        self.last_position = 0
        self.max_drawdown = 0.0
        self.peak_pnl = 0.0
        self.last_mid_price = 0.0
        
    def reset(self, seed=None, options=None) -> Tuple[np.ndarray, Dict]:
        super().reset(seed=seed)
        
        initial_state = self.simulator.reset(seed=seed)
        self.last_total_pnl = 0.0
        self.last_realized_pnl = 0.0
        self.last_position = 0
        self.max_drawdown = 0.0
        self.peak_pnl = 0.0
        self.last_mid_price = initial_state.get("mid_price", 0.0) or 0.0

        return self._extract_obs(initial_state), {}

    def _get_rl_agent(self) -> RLAgent:
        agent = self.simulator.get_agent(self.rl_agent_id)
        if not isinstance(agent, RLAgent):
            raise RuntimeError(f"Simulator does not contain RLAgent('{self.rl_agent_id}')")
        return agent
        
    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        rl_agent = self._get_rl_agent()
        quoted_spread, quoted_skew, quoted_qty = rl_agent.decode_action(action)

        state = self.simulator.get_market_state()
        mid = state['mid_price']

        rl_agent.set_action(action)
        next_state = self.simulator.step()
        num_cancels = rl_agent.consume_last_cancel_count()
        effective_spread, effective_skew, effective_qty = rl_agent.get_last_effective_action()

        # Compute Rewards
        current_pnl = self._get_agent_pnl()
        current_realized = rl_agent.realized_pnl
        position = self._get_agent_inventory()

        pnl_diff = current_pnl - self.last_total_pnl
        realized_diff = current_realized - self.last_realized_pnl
        self.last_total_pnl = current_pnl
        self.last_realized_pnl = current_realized

        # Track drawdown
        self.peak_pnl = max(self.peak_pnl, current_pnl)
        drawdown = self.peak_pnl - current_pnl
        self.max_drawdown = max(self.max_drawdown, drawdown)

        max_inventory = float(max(1, rl_agent.max_inventory))
        inventory_ratio = position / max_inventory
        active_quotes = sum(1 for order in rl_agent.active_orders.values() if order.remaining_quantity > 0)

        pnl_scale = max(25.0, rl_agent.initial_capital * 0.0005)
        drawdown_scale = max(50.0, rl_agent.initial_capital * 0.001)
        next_mid = next_state.get("mid_price", mid) or mid or 0.0
        mid_change_bps = 0.0
        if mid and next_mid:
            mid_change_bps = ((next_mid - mid) / mid) * 10_000.0

        spread_capture_reward = realized_diff / pnl_scale
        mark_to_market_reward = 0.5 * (pnl_diff / pnl_scale)
        inventory_penalty = 0.35 * (inventory_ratio ** 2)
        inventory_carry_penalty = 0.05 * abs(inventory_ratio)
        cancel_penalty = 0.004 * num_cancels
        drawdown_penalty = drawdown / drawdown_scale
        adverse_selection_penalty = max(0.0, -(inventory_ratio * mid_change_bps)) * 0.01
        closeout_penalty = 0.2 * abs(inventory_ratio) if next_state["time_to_close"] / max(1.0, self.simulator.duration_seconds) < 0.1 else 0.0
        two_sided_bonus = 0.03 if active_quotes >= 2 else (-0.02 if active_quotes == 0 else 0.0)
        quote_quality_bonus = 0.01 if effective_spread <= max(self._get_rl_agent().min_spread * 2.0, state.get("spread", 0.0) * 1.6) else 0.0

        reward = (
            spread_capture_reward
            + mark_to_market_reward
            + two_sided_bonus
            + quote_quality_bonus
            - inventory_penalty
            - inventory_carry_penalty
            - cancel_penalty
            - drawdown_penalty
            - adverse_selection_penalty
            - closeout_penalty
        )

        self.last_position = position
        self.last_mid_price = next_mid

        obs = self._extract_obs(next_state)
        done = next_state['time_to_close'] <= 0
        truncated = False 
        
        # Pass info dict for evaluation callbacks
        info = {
            "pnl": current_pnl,
            "realized_pnl": current_realized,
            "inventory": position,
            "mid_price": mid,
            "drawdown": drawdown,
            "cancel_penalty": cancel_penalty,
            "inventory_penalty": inventory_penalty,
            "inventory_carry_penalty": inventory_carry_penalty,
            "adverse_selection_penalty": adverse_selection_penalty,
            "closeout_penalty": closeout_penalty,
            "spread_capture_reward": spread_capture_reward,
            "mark_to_market_reward": mark_to_market_reward,
            "quoted_spread": quoted_spread,
            "quoted_skew": quoted_skew,
            "quoted_size": quoted_qty,
            "effective_spread": effective_spread,
            "effective_skew": effective_skew,
            "effective_size": effective_qty,
            "fill_rate": next_state.get("fill_rate", 0.0),
            "spread": next_state.get("spread", 0.0),
            "active_quotes": active_quotes,
        }

        return obs, reward, done, truncated, info

    def _extract_obs(self, state: Dict) -> np.ndarray:
        return extract_market_maker_observation(self.simulator, self.rl_agent_id)

    def _get_agent_pnl(self) -> float:
        agent = self.simulator.get_agent(self.rl_agent_id)
        if agent is not None:
            mid = self.simulator.get_market_state()['mid_price']
            return agent.realized_pnl + agent.get_unrealized_pnl(mid)
        return 0.0
        
    def _get_agent_inventory(self) -> int:
        agent = self.simulator.get_agent(self.rl_agent_id)
        if agent is not None:
            return agent.position
        return 0
