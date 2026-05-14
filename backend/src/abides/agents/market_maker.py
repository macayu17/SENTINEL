"""ABIDES-style market maker."""

from __future__ import annotations

from typing import List

from .base import Agent
from ..messages import Message, OrderMessage
from ...market.order import OrderSide, OrderType


class MarketMakerAgent(Agent):
    def __init__(self, agent_id: str, wakeup_interval: float = 1.0, spread: float = 0.1, size: int = 100) -> None:
        super().__init__(agent_id, agent_type="MarketMaker", wakeup_interval=wakeup_interval, latency_seconds=0.00005)
        self.spread = spread
        self.size = size

    def on_wakeup(self, timestamp: float) -> List[Message]:
        mid = self.last_mid
        bid = mid - self.spread / 2
        ask = mid + self.spread / 2
        return [
            OrderMessage(self.agent_id, OrderSide.BUY, OrderType.LIMIT, bid, self.size, timestamp=timestamp),
            OrderMessage(self.agent_id, OrderSide.SELL, OrderType.LIMIT, ask, self.size, timestamp=timestamp),
        ]
