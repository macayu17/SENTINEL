"""ABIDES-style noise trader."""

from __future__ import annotations

import random
from typing import List

from .base import Agent
from ..messages import Message, OrderMessage
from ...market.order import OrderSide, OrderType


class NoiseAgent(Agent):
    def __init__(self, agent_id: str, wakeup_interval: float = 1.0, order_rate: float = 0.5) -> None:
        super().__init__(agent_id, agent_type="Noise", wakeup_interval=wakeup_interval, latency_seconds=0.01)
        self.order_rate = order_rate
        self.rng = random.Random(agent_id)

    def on_wakeup(self, timestamp: float) -> List[Message]:
        if self.rng.random() > self.order_rate:
            return []

        side = OrderSide.BUY if self.rng.random() < 0.5 else OrderSide.SELL
        order_type = OrderType.MARKET if self.rng.random() < 0.5 else OrderType.LIMIT
        qty = self.rng.randint(10, 200)
        price = self.last_mid + self.rng.uniform(-0.5, 0.5)
        return [OrderMessage(self.agent_id, side, order_type, price, qty, timestamp=timestamp)]
