"""Informed agent — trades on directional signals with finite horizon."""

from typing import List, Dict, Optional
import random
from collections import deque
from .base_agent import BaseAgent
from ..market.order import Order, OrderSide, OrderType


class InformedAgent(BaseAgent):
    """
    Uses short-term vs long-term moving average crossovers to detect momentum,
    then executes aggressive market orders in the signal direction.
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
        self._short_history: deque = deque(maxlen=10)
        self._long_history: deque = deque(maxlen=50)

    def decide_action(self, market_state: Dict) -> List[Order]:
        price = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        self._short_history.append(price)
        self._long_history.append(price)
        orders: List[Order] = []

        if len(self._long_history) < 50:
            return orders
            
        short_sma = sum(self._short_history) / len(self._short_history)
        long_sma = sum(self._long_history) / len(self._long_history)
        momentum_signal = (short_sma - long_sma) / long_sma
        
        if abs(momentum_signal) > 0.002:
            side = OrderSide.BUY if momentum_signal > 0 else OrderSide.SELL
            current_pos = abs(self.position)
            
            if (self.position > 0 and side == OrderSide.SELL) or (self.position < 0 and side == OrderSide.BUY):
                qty = current_pos + min(300, self.max_position)
            else:
                qty = min(300, self.max_position - current_pos)
                
            if qty > 0:
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
