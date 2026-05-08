"""Policy-controlled RL market maker agent."""

import math
from typing import Dict, List, Optional, Sequence, Tuple
from .base_agent import BaseAgent
from ..market.order import Order, OrderSide, OrderType

class RLAgent(BaseAgent):
    """
    Market-making agent whose policy action is supplied externally by an RL loop.

    The simulator still owns order submission, matching, and position/PnL updates.
    This keeps the RL participant on the same execution path as every other agent.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 100000.0,
        max_inventory: int = 5000,
        min_spread: float = 0.02,
        max_spread: float = 0.52,
        max_skew: float = 0.5,
        min_quote_size: int = 10,
        max_quote_size: int = 110,
    ) -> None:
        super().__init__(agent_id, "RL_MM", initial_capital, latency_seconds=0.0)
        self.max_inventory = max_inventory
        self.min_spread = min_spread
        self.max_spread = max_spread
        self.max_skew = max_skew
        self.min_quote_size = min_quote_size
        self.max_quote_size = max_quote_size
        self.external_action_controlled = True
        self.wakeup_interval = 1.0
        self._pending_action: Optional[Tuple[float, float, float]] = None
        self._last_cancel_count: int = 0
        self._last_effective_action: Tuple[float, float, int] = (
            self.min_spread,
            0.0,
            self.min_quote_size,
        )

    def set_action(self, action: Sequence[float]) -> None:
        """Set the normalized policy action for the next simulator step."""
        if len(action) != 3:
            raise ValueError(f"RL action must have exactly 3 elements, got {len(action)}")
        sanitized = []
        for component in action:
            value = float(component)
            if not math.isfinite(value):
                value = 0.0
            sanitized.append(max(-1.0, min(1.0, value)))
        self._pending_action = tuple(sanitized)

    def consume_last_cancel_count(self) -> int:
        """Return the number of successful cancellations from the last action cycle."""
        count = self._last_cancel_count
        self._last_cancel_count = 0
        return count

    def note_cancel_result(self, cancelled: bool) -> None:
        """Record whether a requested cancellation succeeded on-book."""
        if cancelled:
            self._last_cancel_count += 1

    def get_last_effective_action(self) -> Tuple[float, float, int]:
        """Return the final market-adapted quote controls used on the last step."""
        return self._last_effective_action

    def decode_action(self, action: Sequence[float]) -> Tuple[float, float, int]:
        """Map normalized policy output into spread, skew, and quote size."""
        spread_act, skew_act, size_act = action
        actual_spread = ((spread_act + 1.0) / 2.0) * (self.max_spread - self.min_spread) + self.min_spread
        actual_spread = min(max(actual_spread, self.min_spread), self.max_spread)
        actual_skew = min(max(skew_act * self.max_skew, -self.max_skew), self.max_skew)
        qty_span = self.max_quote_size - self.min_quote_size
        actual_qty = int(((size_act + 1.0) / 2.0) * qty_span + self.min_quote_size)
        actual_qty = min(max(actual_qty, self.min_quote_size), self.max_quote_size)
        return actual_spread, actual_skew, actual_qty

    def _contextualize_action(
        self,
        market_state: Dict,
        spread: float,
        skew: float,
        quantity: int,
    ) -> Tuple[float, float, int]:
        """Blend policy intent with market-making safeguards."""
        current_spread = float(market_state.get("spread", 0.0) or 0.0)
        volatility = max(0.0, float(market_state.get("volatility", 0.0) or 0.0))
        imbalance = max(-1.0, min(1.0, float(market_state.get("order_book_imbalance", 0.0) or 0.0)))
        signed_volume = float(market_state.get("recent_signed_volume", 0.0) or 0.0)
        time_to_close = max(0.0, float(market_state.get("time_to_close", 0.0) or 0.0))

        inventory_ratio = self.position / float(max(1, self.max_inventory))
        flow_pressure = max(-1.0, min(1.0, imbalance + (0.5 * math.tanh(signed_volume / 1200.0))))

        spread_floor = max(self.min_spread, current_spread * 1.1) if current_spread > 0 else self.min_spread
        vol_buffer = min(0.18, volatility * 0.02)
        inventory_buffer = min(0.08, abs(inventory_ratio) * 0.06)
        adjusted_spread = min(
            self.max_spread,
            max(spread_floor, spread) + vol_buffer + inventory_buffer,
        )

        inventory_skew = max(-0.25, min(0.25, inventory_ratio * 0.22))
        flow_skew = max(-0.18, min(0.18, -flow_pressure * 0.12))
        adjusted_skew = max(
            -self.max_skew,
            min(self.max_skew, skew + inventory_skew + flow_skew),
        )

        size_scale = 1.0 - min(0.7, (abs(inventory_ratio) * 0.55) + (volatility * 0.08))
        if time_to_close < 300.0:
            size_scale *= 0.75
        if abs(inventory_ratio) > 0.85:
            size_scale *= 0.5

        adjusted_qty = int(round(quantity * max(0.35, size_scale)))
        adjusted_qty = min(max(adjusted_qty, self.min_quote_size), self.max_quote_size)
        return adjusted_spread, adjusted_skew, adjusted_qty

    def consume_cancellations(self) -> List[str]:
        """
        Replace the previous quote set only when a fresh action has been supplied.
        """
        self._last_cancel_count = 0
        if self._pending_action is None:
            return []
        return self.cancel_all_active_orders()

    def decide_action(self, market_state: Dict) -> List[Order]:
        if self._pending_action is None:
            return []

        action = self._pending_action
        self._pending_action = None

        mid = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        if mid <= 0:
            return []

        actual_spread, actual_skew, actual_qty = self.decode_action(action)
        actual_spread, actual_skew, actual_qty = self._contextualize_action(
            market_state,
            actual_spread,
            actual_skew,
            actual_qty,
        )
        self._last_effective_action = (actual_spread, actual_skew, actual_qty)
        bid_price = round(mid - (actual_spread / 2) - actual_skew, 2)
        ask_price = round(mid + (actual_spread / 2) - actual_skew, 2)

        # Ensure quotes remain ordered by at least one tick.
        if bid_price >= ask_price:
            ask_price = round(bid_price + 0.01, 2)

        orders: List[Order] = []

        # If inventory is at the limit, only quote the side that reduces exposure.
        if self.position <= -self.max_inventory:
            orders.append(
                Order(
                    agent_id=self.agent_id,
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    price=bid_price,
                    quantity=actual_qty,
                )
            )
            return orders

        if self.position >= self.max_inventory:
            orders.append(
                Order(
                    agent_id=self.agent_id,
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    price=ask_price,
                    quantity=actual_qty,
                )
            )
            return orders

        orders.append(
            Order(
                agent_id=self.agent_id,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                price=bid_price,
                quantity=actual_qty,
            )
        )
        orders.append(
            Order(
                agent_id=self.agent_id,
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT,
                price=ask_price,
                quantity=actual_qty,
            )
        )
        return orders

    def reset(self) -> None:
        super().reset()
        self._pending_action = None
        self._last_cancel_count = 0
        self._last_effective_action = (self.min_spread, 0.0, self.min_quote_size)
