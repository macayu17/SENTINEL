"""Liquidity trader agent — executes exogenous buy/sell pressure via sliced orders."""

from typing import List, Dict
import random
from .base_agent import BaseAgent
from .risk import AgentRiskProfile, displayed_depth_for_side, near_touch_price
from ..market.order import Order, OrderSide, OrderType


class LiquidityTraderAgent(BaseAgent):
    """
    Represents a non-strategic liquidity demander/supplier.

    Behavior:
    - Starts a parent order intermittently (buy or sell exogenous need).
    - Splits parent order into smaller child slices over time.
    - Uses a mix of market and near-touch limit orders.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 2_000_000.0,
        wakeup_interval: float = 1.5,
        start_probability: float = 0.02,
        min_parent_qty: int = 2_000,
        max_parent_qty: int = 10_000,
        min_child_qty: int = 50,
        max_child_qty: int = 300,
    ) -> None:
        super().__init__(agent_id, "LiquidityTrader", initial_capital, latency_seconds=0.02)
        self.wakeup_interval = wakeup_interval
        self.start_probability = start_probability
        self.min_parent_qty = min_parent_qty
        self.max_parent_qty = max_parent_qty
        self.min_child_qty = min_child_qty
        self.max_child_qty = max_child_qty

        self._active_side: OrderSide | None = None
        self._remaining_parent_qty: int = 0
        self.risk_profile = AgentRiskProfile(
            max_inventory=max_parent_qty,
            base_order_size=max_child_qty,
            min_order_size=min_child_qty,
            participation_rate=0.12,
            max_active_orders=2,
            stale_ticks=4,
        )

    def decide_action(self, market_state: Dict) -> List[Order]:
        orders: List[Order] = []
        mid = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        volatility = float(market_state.get("volatility", 0.0) or 0.0)

        if self._remaining_parent_qty <= 0:
            if random.random() < self.start_probability:
                self._active_side = random.choice([OrderSide.BUY, OrderSide.SELL])
                self._remaining_parent_qty = random.randint(self.min_parent_qty, self.max_parent_qty)
            return orders
        if self._active_side is None:
            self._remaining_parent_qty = 0
            return orders

        depth_limited_qty = self.risk_profile.target_size(
            side=self._active_side,
            position=self.position,
            available_depth=displayed_depth_for_side(market_state, self._active_side),
            volatility=volatility,
            active_orders=self.active_orders,
            aggression=1.1,
        )
        child_qty = min(
            self._remaining_parent_qty,
            random.randint(self.min_child_qty, self.max_child_qty),
            depth_limited_qty,
        )
        if child_qty <= 0:
            return orders
        self._remaining_parent_qty -= child_qty

        # More aggressive when spread is tight, otherwise lean to passive near-touch limits.
        spread = market_state.get("spread", 0.05)
        use_market = random.random() < (0.55 if spread <= 0.08 else 0.35)

        if use_market:
            orders.append(
                Order(
                    agent_id=self.agent_id,
                    side=self._active_side,
                    order_type=OrderType.MARKET,
                    price=mid,
                    quantity=child_qty,
                )
            )
        else:
            px = near_touch_price(mid, self._active_side, spread)
            orders.append(
                Order(
                    agent_id=self.agent_id,
                    side=self._active_side,
                    order_type=OrderType.LIMIT,
                    price=round(px, 2),
                    quantity=child_qty,
                )
            )

        return orders

    def reset(self) -> None:
        super().reset()
        self._active_side = None
        self._remaining_parent_qty = 0

    def cancel_for_state(self, market_state: Dict) -> List[str]:
        if not self.active_orders:
            return []
        if self._active_side is None:
            return self.cancel_all_active_orders()
        mid = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        spread = market_state.get("spread", 0.05)
        target = near_touch_price(mid, self._active_side, spread)
        if self.risk_profile.should_reprice(
            self.active_orders,
            target_bid=target if self._active_side == OrderSide.BUY else mid,
            target_ask=target if self._active_side == OrderSide.SELL else mid,
        ):
            return self.cancel_all_active_orders()
        return []
