"""Informed agent — trades on directional signals with finite horizon."""

from typing import List, Dict, Optional
import random
from .base_agent import BaseAgent
from ..market.order import Order, OrderSide, OrderType


class InformedAgent(BaseAgent):
    """
    Has a small probability each wake of receiving private information.
    When informed, trades aggressively in the signal direction
    until the signal expires.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 5_000_000.0,
        signal_probability: float = 0.01,
        signal_accuracy: float = 0.70,
        signal_duration: int = 120,
        max_position: int = 5000,
    ) -> None:
        super().__init__(agent_id, "Informed", initial_capital, latency_seconds=0.005)
        self.wakeup_interval = 0.6
        self.signal_probability = signal_probability
        self.signal_accuracy = signal_accuracy
        self.signal_duration = signal_duration
        self.max_position = max_position

        self._active_signal: Optional[str] = None  # "buy" or "sell"
        self._signal_start_time: float = 0.0

    def decide_action(self, market_state: Dict) -> List[Order]:
        current_time = market_state.get("current_time", 0.0)
        price = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        flow = market_state.get("recent_signed_volume", 0.0)
        imbalance = market_state.get("order_book_imbalance", 0.0)
        trend = market_state.get("recent_price_change", 0.0)
        orders: List[Order] = []

        if self._active_signal and (current_time - self._signal_start_time) > self.signal_duration:
            if self.position != 0:
                side = OrderSide.SELL if self.position > 0 else OrderSide.BUY
                orders.append(
                    Order(
                        agent_id=self.agent_id,
                        side=side,
                        order_type=OrderType.MARKET,
                        price=price,
                        quantity=abs(self.position),
                    )
                )
            self._active_signal = None
            return orders

        if not self._active_signal and random.random() < self.signal_probability:
            score = 0.8 * trend + 0.15 * imbalance + 0.05 * (
                1 if flow > 0 else -1 if flow < 0 else 0
            )
            if abs(score) < 1e-9:
                direction = "buy" if random.random() < 0.5 else "sell"
            else:
                direction = "buy" if score > 0 else "sell"

            if random.random() > self.signal_accuracy:
                direction = "sell" if direction == "buy" else "buy"
            self._active_signal = direction
            self._signal_start_time = current_time

        if self._active_signal:
            side = OrderSide.BUY if self._active_signal == "buy" else OrderSide.SELL
            current_pos = abs(self.position)
            if current_pos < self.max_position:
                qty = min(500, self.max_position - current_pos)
                orders.append(
                    Order(
                        agent_id=self.agent_id,
                        side=side,
                        order_type=OrderType.MARKET,
                        price=price,
                        quantity=qty,
                    )
                )

        return orders
