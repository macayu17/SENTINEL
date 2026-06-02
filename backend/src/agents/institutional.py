"""Institutional agent — executes large orders via TWAP over a time window."""

from typing import List, Dict
from .base_agent import BaseAgent
from .risk import AgentRiskProfile, near_touch_price, risk_limited_order
from ..market.order import Order, OrderSide, OrderType
import random


class InstitutionalAgent(BaseAgent):
    """
    Executes a large order using TWAP (Time-Weighted Average Price) slicing.
    Splits the target quantity into intervals over the execution window.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 100_000_000.0,
        target_quantity: int = 50_000,
        execution_window: int = 3600,
        slice_interval: int = 60,
        max_slice_size: int = 1000,
        start_after_seconds: float | None = None,
    ) -> None:
        super().__init__(agent_id, "Institutional", initial_capital, latency_seconds=0.01)
        self.target_quantity = target_quantity
        self.execution_window = execution_window
        self.slice_interval = slice_interval
        self.max_slice_size = max_slice_size
        self.start_after_seconds = start_after_seconds
        self.executed_quantity: int = 0
        self.side: OrderSide = random.choice([OrderSide.BUY, OrderSide.SELL])
        self._last_slice_time: float = 0.0
        self._start_time: float = 0.0
        self._started: bool = False
        self._scheduled_start_time: float = self._next_start_time()
        self.risk_profile = AgentRiskProfile(
            max_inventory=max(target_quantity, max_slice_size),
            base_order_size=max_slice_size,
            min_order_size=max(10, max_slice_size // 20),
            participation_rate=0.15,
            max_active_orders=2,
            stale_ticks=4,
        )

    def decide_action(self, market_state: Dict) -> List[Order]:
        current_time = market_state.get("current_time", 0.0)
        price = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        spread = float(market_state.get("spread", 0.05) or 0.05)
        volatility = float(market_state.get("volatility", 0.0) or 0.0)
        orders: List[Order] = []

        if self.active_orders and self._has_fresh_active_order(market_state):
            return orders

        # Already done
        if self.executed_quantity >= self.target_quantity:
            return orders

        # Start execution at a random point in the session
        if not self._started:
            if current_time < self._scheduled_start_time:
                return orders
            self._started = True
            self._start_time = self._scheduled_start_time
            self._last_slice_time = self._scheduled_start_time

        # TWAP: slice at regular intervals
        elapsed_since_slice = current_time - self._last_slice_time
        if elapsed_since_slice >= self.slice_interval:
            remaining = self.target_quantity - self.executed_quantity
            elapsed_execution = max(0.0, current_time - self._start_time)
            num_remaining_slices = max(
                1,
                int((self.execution_window - elapsed_execution) / self.slice_interval),
            )
            twap_size = min(
                remaining,
                self.max_slice_size,
                remaining // num_remaining_slices + 1,
            )
            urgent = elapsed_execution > self.execution_window * 0.85
            order_type = OrderType.MARKET if urgent and spread <= 0.05 else OrderType.LIMIT
            order = risk_limited_order(
                self.risk_profile,
                agent_id=self.agent_id,
                side=self.side,
                order_type=order_type,
                price=price if order_type == OrderType.MARKET else near_touch_price(price, self.side, spread),
                position=self.position,
                market_state=market_state,
                volatility=volatility,
                aggression=1.0,
                quantity_cap=twap_size,
            )
            if order is not None:
                orders.append(order)
                self._last_slice_time = current_time

        return orders

    def _next_start_time(self) -> float:
        if self.start_after_seconds is not None:
            return max(0.0, float(self.start_after_seconds))
        latest = max(float(self.slice_interval), min(600.0, self.execution_window * 0.2))
        return random.uniform(0.0, latest)

    def update_position(self, trade) -> None:
        super().update_position(trade)
        self.executed_quantity = abs(self.position)

    def reset(self) -> None:
        super().reset()
        self.executed_quantity = 0
        self.side = random.choice([OrderSide.BUY, OrderSide.SELL])
        self._last_slice_time = 0.0
        self._start_time = 0.0
        self._started = False
        self._scheduled_start_time = self._next_start_time()

    def cancel_for_state(self, market_state: Dict) -> List[str]:
        if not self.active_orders:
            return []
        if self._has_fresh_active_order(market_state):
            return []
        return self.cancel_all_active_orders()

    def _has_fresh_active_order(self, market_state: Dict) -> bool:
        price = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        spread = float(market_state.get("spread", 0.05) or 0.05)
        target = near_touch_price(price, self.side, spread)
        return not self.risk_profile.should_reprice(
            self.active_orders,
            target_bid=target if self.side == OrderSide.BUY else price,
            target_ask=target if self.side == OrderSide.SELL else price,
        )
