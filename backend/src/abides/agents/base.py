"""ABIDES-style base agent."""

from __future__ import annotations

from typing import List, Optional

from ..kernel import EventKernel
from ..messages import Message, MarketDataMessage, TradeMessage


class Agent:
    def __init__(
        self,
        agent_id: str,
        agent_type: str = "Agent",
        wakeup_interval: float = 1.0,
        latency_seconds: float = 0.0,
        initial_cash: float = 0.0,
    ) -> None:
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.wakeup_interval = wakeup_interval
        self.latency_seconds = latency_seconds
        self.kernel: Optional[EventKernel] = None
        self.simulation = None
        self.position: int = 0
        self.initial_cash = initial_cash
        self.cash: float = initial_cash
        self.last_mid: float = 100.0
        self.last_oracle: Optional[dict] = None

    def bind(self, kernel: EventKernel, simulation) -> None:
        self.kernel = kernel
        self.simulation = simulation

    def on_start(self) -> None:
        """Hook for initialization."""

    def on_wakeup(self, timestamp: float) -> List[Message]:
        """Return outbound messages for this wakeup."""
        return []

    def on_message(self, message: Message) -> None:
        """Handle inbound messages from the exchange."""
        if isinstance(message, MarketDataMessage):
            if message.mid_price:
                self.last_mid = message.mid_price
            if message.oracle is not None:
                self.last_oracle = message.oracle
        if isinstance(message, TradeMessage):
            self._handle_trade(message)

    def _handle_trade(self, message: TradeMessage) -> None:
        if self.agent_id == message.buyer_id:
            self.position += message.quantity
            self.cash -= message.price * message.quantity
        elif self.agent_id == message.seller_id:
            self.position -= message.quantity
            self.cash += message.price * message.quantity

    def get_metrics(self, current_price: float) -> dict:
        mark = current_price * self.position
        total = self.cash + mark - self.initial_cash
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "position": self.position,
            "total_pnl": round(total, 4),
            "realized_pnl": round(self.cash - self.initial_cash, 4),
            "unrealized_pnl": round(mark, 4),
            "sharpe_ratio": 0.0,
            "num_trades": 0,
        }
