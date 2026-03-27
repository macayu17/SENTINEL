"""Gymnasium environment for training Reinforcement Learning agents in the limit order book."""

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Dict, Any, Tuple
from .simulator import MarketSimulator
from .order import Order, OrderSide, OrderType
import uuid

class MarketMakerEnv(gym.Env):
    """
    RL Environment where the agent acts as a Market Maker.
    Actions: Continuous[spread, skew, size] 
      - spread (-1 to 1): Distance between quotes.
      - skew (-1 to 1): Inventory bias (offsets quotes).
      - size (-1 to 1): Quantity of shares to offer.
    Observations: Vector of 10 market variables.
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
        self.last_pnl = 0.0
        self.last_position = 0
        self.max_drawdown = 0.0
        self.peak_pnl = 0.0
        self.active_order_ids = []
        
    def reset(self, seed=None, options=None) -> Tuple[np.ndarray, Dict]:
        super().reset(seed=seed)
        
        initial_state = self.simulator.reset(seed=seed)
        self.last_pnl = 0.0
        self.last_position = 0
        self.max_drawdown = 0.0
        self.peak_pnl = 0.0
        self.active_order_ids = []
        
        return self._extract_obs(initial_state), {}
        
    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        spread_act, skew_act, size_act = action
        
        # Decode actions to actual market parameters
        actual_spread = np.clip((spread_act + 1.0) * 0.25 + 0.02, 0.02, 1.00) # Spread from 0.02 to 0.52
        actual_skew = np.clip(skew_act * 0.5, -0.5, 0.5)      # Skew from -0.5 to 0.5
        actual_qty = int(np.clip((size_act + 1.0) * 50 + 10, 10, 110)) # Qty from 10 to 110
        
        # Cancel previous orders to avoid self-crossing and excessive accumulation
        num_cancels = 0
        for oid in self.active_order_ids:
            if self.simulator.order_book.cancel_order(oid):
                num_cancels += 1
        self.active_order_ids.clear()
        
        # Insert new quotes based on current market mid
        state = self.simulator.get_market_state()
        mid = state['mid_price']
        
        bid_price = round(mid - (actual_spread / 2) - actual_skew, 2)
        ask_price = round(mid + (actual_spread / 2) - actual_skew, 2)
        
        b_order = Order(agent_id=self.rl_agent_id, side=OrderSide.BUY, order_type=OrderType.LIMIT, price=bid_price, quantity=actual_qty)
        a_order = Order(agent_id=self.rl_agent_id, side=OrderSide.SELL, order_type=OrderType.LIMIT, price=ask_price, quantity=actual_qty)
        
        # Need unique IDs for cancellation
        b_order.order_id = str(uuid.uuid4())
        a_order.order_id = str(uuid.uuid4())
        
        self.simulator.order_book.add_order(b_order)
        self.simulator.order_book.add_order(a_order)
        self.active_order_ids.extend([b_order.order_id, a_order.order_id])
        
        # Advance environment 1 second equivalent in simulator time
        next_state = self.simulator.step()
        
        # Compute Rewards
        current_pnl = self._get_agent_pnl()
        position = self._get_agent_inventory()
        
        pnl_diff = current_pnl - self.last_pnl
        self.last_pnl = current_pnl
        
        # Track drawdown
        old_max_dd = self.max_drawdown
        self.peak_pnl = max(self.peak_pnl, current_pnl)
        drawdown = self.peak_pnl - current_pnl
        self.max_drawdown = max(self.max_drawdown, drawdown)
        
        # Shaping penalties
        inventory_penalty = 0.001 * abs(position) 
        cancel_penalty = 0.01 * num_cancels
        drawdown_penalty = 0.5 * max(0.0, self.max_drawdown - old_max_dd)
        
        # Add carry penalty so lingering inventory over time is discouraged.
        inventory_carry_penalty = 0.0005 * abs(position)

        # Spooner-like inventory-aware asymmetric reward.
        reward = pnl_diff - inventory_penalty - inventory_carry_penalty - cancel_penalty - drawdown_penalty
        
        # Basic safety guard: prevent NaNs and clip extreme values to maintain stable PPO gradients
        reward = float(np.clip(np.nan_to_num(reward, nan=0.0), -100.0, 100.0))
        
        self.last_position = position
        
        obs = self._extract_obs(next_state)
        done = next_state['time_to_close'] <= 0
        truncated = False 
        
        # Pass info dict for evaluation callbacks
        info = {
            "pnl": current_pnl,
            "inventory": position,
            "mid_price": mid,
            "drawdown": drawdown,
            "cancel_penalty": cancel_penalty,
            "inventory_penalty": inventory_penalty,
            "inventory_carry_penalty": inventory_carry_penalty,
            "fill_rate": next_state.get("fill_rate", 0.0),
            "spread": next_state.get("spread", 0.0),
        }
        
        return obs, reward, done, truncated, info

    def _extract_obs(self, state: Dict) -> np.ndarray:
        ref_px = 100.0 if state['mid_price'] == 0 else state['mid_price']
        
        best_bid = (state['best_bid'] - ref_px) / ref_px if state['best_bid'] else 0.0
        best_ask = (state['best_ask'] - ref_px) / ref_px if state['best_ask'] else 0.0
        spread = state['spread'] / ref_px
        mid = (state['mid_price'] - 100.0) / 100.0 # Normalized against initial start
        
        b_depth, a_depth = state['bid_depth'], state['ask_depth']
        imbalance = (b_depth - a_depth) / max(b_depth + a_depth, 1)
        
        agent = None
        for a in self.simulator.agents:
            if a.agent_id == self.rl_agent_id:
                agent = a
                break
                
        inventory = agent.position / 500.0 if agent else 0.0
        realized = (agent.realized_pnl / max(1.0, agent.initial_capital)) if agent else 0.0
        unrealized = ((agent.get_unrealized_pnl(state['mid_price']) / max(1.0, agent.initial_capital)) if agent else 0.0)
        
        vol = state['volatility']
        recent_px_chg = state.get('recent_price_change', 0.0)
        signed_vol = state.get('recent_signed_volume', 0.0) / 1000.0
        fill_rate = state.get('fill_rate', 0.0) / 10.0
        time = state['time_to_close'] / self.simulator.duration_seconds
        
        return np.array([
            best_bid, best_ask, spread, mid, imbalance,
            recent_px_chg, signed_vol,
            inventory, realized, unrealized,
            vol, fill_rate, time
        ], dtype=np.float32)

    def _get_agent_pnl(self) -> float:
        for a in self.simulator.agents:
            if a.agent_id == self.rl_agent_id:
                mid = self.simulator.get_market_state()['mid_price']
                return a.capital - a.initial_capital + (a.position * mid)
        return 0.0
        
    def _get_agent_inventory(self) -> int:
        for a in self.simulator.agents:
            if a.agent_id == self.rl_agent_id:
                return a.position
        return 0
