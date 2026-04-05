import re

def update_institutional():
    with open('backend/src/agents/institutional.py', 'r') as f:
        text = f.read()

    new_decide_action = '''    def decide_action(self, market_state: Dict) -> List[Order]:
        current_time = market_state.get("current_time", 0.0)
        price = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        spread = market_state.get("spread", 0.05)
        orders: List[Order] = []

        if self.executed_quantity >= self.target_quantity:
            return orders

        if not self._started:
            if random.random() < 0.01:
                self._started = True
                self._last_slice_time = current_time
            return orders

        elapsed_since_slice = current_time - self._last_slice_time
        if elapsed_since_slice >= self.slice_interval:
            remaining = self.target_quantity - self.executed_quantity
            
            total_elapsed = current_time - (self._last_slice_time - elapsed_since_slice)
            expected_executed = int((total_elapsed / self.execution_window) * self.target_quantity)
            behind_schedule = self.executed_quantity < expected_executed

            num_remaining_slices = max(1, int((self.execution_window - total_elapsed) / self.slice_interval))
            slice_size = min(remaining, self.max_slice_size, remaining // num_remaining_slices + 1)
            
            if slice_size > 0:
                order_type = OrderType.MARKET if behind_schedule else OrderType.LIMIT
                offset = spread * 0.4
                limit_px = round(price - offset if self.side == OrderSide.BUY else price + offset, 2)
                
                orders.append(
                    Order(
                        agent_id=self.agent_id,
                        side=self.side,
                        order_type=order_type,
                        price=price if behind_schedule else limit_px,
                        quantity=slice_size,
                    )
                )
                self.executed_quantity += slice_size
                self._last_slice_time = current_time

        return orders'''

    text = re.sub(r'    def decide_action\(self, market_state: Dict\) -> List\[Order\]:.*', new_decide_action, text, flags=re.DOTALL)

    with open('backend/src/agents/institutional.py', 'w') as f:
        f.write(text)

def update_hft():
    with open('backend/src/agents/hft_agent.py', 'r') as f:
        text = f.read()
        
    old_hft = '''        if spread >= 0.02 and abs(imbalance) > 0.2:
            quote_side = OrderSide.BUY if imbalance > 0 else OrderSide.SELL
            quote_px = (
                round(price - 0.01, 2)
                if quote_side == OrderSide.BUY
                else round(price + 0.01, 2)
            )
            orders.append(
                Order(
                    agent_id=self.agent_id,
                    side=quote_side,
                    order_type=OrderType.LIMIT,
                    price=quote_px,
                    quantity=25,
                )
            )

        return orders'''

    new_hft = '''        if abs(imbalance) > 0.65 and self.position != 0:
            exit_side = OrderSide.SELL if self.position > 0 else OrderSide.BUY
            orders.append(
                Order(
                    agent_id=self.agent_id,
                    side=exit_side,
                    order_type=OrderType.MARKET,
                    price=price,
                    quantity=abs(self.position),
                )
            )
            return orders

        if spread >= 0.04:
            orders.append(
                Order(
                    agent_id=self.agent_id,
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    price=round(price + 0.01, 2),
                    quantity=50,
                )
            )
            orders.append(
                Order(
                    agent_id=self.agent_id,
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    price=round(price - 0.01, 2),
                    quantity=50,
                )
            )

        return orders'''

    text = text.replace(old_hft, new_hft)
    with open('backend/src/agents/hft_agent.py', 'w') as f:
        f.write(text)

def update_informed():
    with open('backend/src/agents/informed.py', 'r') as f:
        text = f.read()

    new_informed = '''"""Informed agent — trades on directional signals with finite horizon."""

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
'''
    with open('backend/src/agents/informed.py', 'w') as f:
        f.write(new_informed)

if __name__ == '__main__':
    update_institutional()
    update_hft()
    update_informed()
    print("Agent updates complete.")
