"""ABIDES-style market maker."""

from __future__ import annotations

from typing import List

from .base import Agent
from ..messages import CancelMessage, Message, OrderMessage
from ...market.order import OrderSide, OrderType


class MarketMakerAgent(Agent):
    def __init__(self, agent_id: str, wakeup_interval: float = 1.0, spread: float = 0.1, size: int = 100) -> None:
        super().__init__(agent_id, agent_type="MarketMaker", wakeup_interval=wakeup_interval, latency_seconds=0.00005)
        self.spread = spread
        self.size = size
        self._quote_order_ids: list[str] = []

    def on_start(self) -> None:
        self._quote_order_ids.clear()

    def on_wakeup(self, timestamp: float) -> List[Message]:
        mid = self.last_mid
        inventory_ratio = max(-1.0, min(1.0, self.position / max(1, self.size * 20)))
        inventory_skew = inventory_ratio * self.spread * 0.5
        bid = mid - self.spread / 2 - inventory_skew
        ask = mid + self.spread / 2 - inventory_skew
        quote_size = max(1, int(self.size * (1.0 - min(0.7, abs(inventory_ratio)))))
        suffix = int(timestamp * 1_000_000)
        bid_order_id = f"{self.agent_id}-BID-{suffix}"
        ask_order_id = f"{self.agent_id}-ASK-{suffix}"

        messages: List[Message] = [
            CancelMessage(self.agent_id, order_id, timestamp=timestamp)
            for order_id in self._quote_order_ids
        ]
        messages.extend(
            [
                OrderMessage(
                    self.agent_id,
                    OrderSide.BUY,
                    OrderType.LIMIT,
                    bid,
                    quote_size,
                    order_id=bid_order_id,
                    timestamp=timestamp,
                ),
                OrderMessage(
                    self.agent_id,
                    OrderSide.SELL,
                    OrderType.LIMIT,
                    ask,
                    quote_size,
                    order_id=ask_order_id,
                    timestamp=timestamp,
                ),
            ]
        )
        self._quote_order_ids = [bid_order_id, ask_order_id]
        return messages
