"""Institutional agent — works a large parent order against a TWAP schedule."""

from typing import List, Dict
from .base_agent import BaseAgent
from .risk import AgentRiskProfile, near_touch_price
from ..market.order import Order, OrderSide, OrderType


class InstitutionalAgent(BaseAgent):
    """
    Works a large parent order over an execution window against a TWAP schedule,
    escalating from passive iceberg slices to marketable ones when fills lag.
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
        super().__init__(agent_id, "Institutional", initial_capital)
        self.target_quantity = target_quantity
        self.execution_window = execution_window
        self.slice_interval = slice_interval
        self.max_slice_size = max_slice_size
        self.start_after_seconds = start_after_seconds
        self.executed_quantity: int = 0
        self.side: OrderSide = self.rng.choice([OrderSide.BUY, OrderSide.SELL])
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
        price = self._mid(market_state)
        spread = float(market_state.get("spread", 0.05) or 0.05)
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

        # Schedule-tracking TWAP: compare fills with a straight-line schedule and pick
        # the urgency from the gap — behind crosses, on-track rests, ahead waits.
        if current_time - self._last_slice_time < self.slice_interval:
            return orders
        remaining = self.target_quantity - self.executed_quantity
        elapsed = max(0.0, current_time - self._start_time)
        scheduled = self.target_quantity * min(1.0, elapsed / max(1.0, self.execution_window))
        behind = scheduled - self.executed_quantity
        remaining_slices = max(1, int((self.execution_window - elapsed) / self.slice_interval))
        twap_size = remaining // remaining_slices + 1
        if behind < -twap_size:
            return orders  # ahead of schedule: let the book come to us
        urgent = behind > 2 * twap_size and spread <= 0.05
        order_type = OrderType.MARKET if urgent else OrderType.LIMIT
        order = self._entry_order(
            market_state,
            self.side,
            order_type,
            price if urgent else near_touch_price(price, self.side, spread),
            quantity_cap=min(remaining, self.max_slice_size, max(0, int(behind)) + twap_size),
        )
        if order is not None:
            # Work resting slices as icebergs so the parent size is not advertised.
            if not urgent and order.quantity > 1:
                order.display_quantity = max(1, order.quantity // 4)
            orders.append(order)
            self._last_slice_time = current_time

        return orders

    def _next_start_time(self) -> float:
        if self.start_after_seconds is not None:
            return max(0.0, float(self.start_after_seconds))
        latest = max(float(self.slice_interval), min(600.0, self.execution_window * 0.2))
        return self.rng.uniform(0.0, latest)

    def update_position(self, trade) -> None:
        filled_parent_side = (
            self.side == OrderSide.BUY and trade.buyer_agent_id == self.agent_id
        ) or (
            self.side == OrderSide.SELL and trade.seller_agent_id == self.agent_id
        )
        super().update_position(trade)
        if filled_parent_side:
            self.executed_quantity = min(
                self.target_quantity,
                self.executed_quantity + trade.quantity,
            )

    def reset(self) -> None:
        super().reset()
        self.executed_quantity = 0
        self.side = self.rng.choice([OrderSide.BUY, OrderSide.SELL])
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
        price = self._mid(market_state)
        spread = float(market_state.get("spread", 0.05) or 0.05)
        target = near_touch_price(price, self.side, spread)
        return not self.risk_profile.should_reprice(
            self.active_orders,
            target_bid=target if self.side == OrderSide.BUY else price,
            target_ask=target if self.side == OrderSide.SELL else price,
        )
