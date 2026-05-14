"""ABIDES-style informed agent that trades on oracle mispricing."""

from __future__ import annotations

from typing import List

from .base import Agent
from ..messages import Message, OrderMessage
from ...market.order import OrderSide, OrderType


class InformedAgent(Agent):
    def __init__(
        self,
        agent_id: str,
        wakeup_interval: float = 1.0,
        mispricing_threshold: float = 0.2,
        max_position: int = 1000,
    ) -> None:
        super().__init__(agent_id, agent_type="Informed", wakeup_interval=wakeup_interval, latency_seconds=0.002)
        self.mispricing_threshold = mispricing_threshold
        self.max_position = max_position

    def on_wakeup(self, timestamp: float) -> List[Message]:
        if not self.last_oracle:
            return []

        mispricing = float(self.last_oracle.get("mispricing", 0.0))
        if abs(mispricing) < self.mispricing_threshold:
            return []

        side = OrderSide.SELL if mispricing > 0 else OrderSide.BUY
        qty = min(200, self.max_position - abs(self.position))
        if qty <= 0:
            return []

        price = self.last_mid
        return [OrderMessage(self.agent_id, side, OrderType.MARKET, price, qty, timestamp=timestamp)]
