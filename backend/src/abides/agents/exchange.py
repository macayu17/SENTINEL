"""ABIDES-style exchange agent."""

from __future__ import annotations

from typing import List, Optional

from ..messages import Message, OrderMessage, CancelMessage, MarketDataMessage, TradeMessage
from ..order_book import AbidesOrderBook
from ...market.order import OrderSide
from ...market.trade import Trade


class ExchangeAgent:
    def __init__(self, exchange_id: str = "EXCHANGE") -> None:
        self.exchange_id = exchange_id
        self.order_book = AbidesOrderBook()
        self.kernel = None
        self.simulation = None
        self.last_price: float = 100.0

    def bind(self, kernel, simulation) -> None:
        self.kernel = kernel
        self.simulation = simulation

    def on_message(self, message: Message, timestamp: float) -> List[Message]:
        if isinstance(message, OrderMessage):
            trades = self.order_book.add_order(
                agent_id=message.sender_id,
                side=message.side,
                order_type=message.order_type,
                price=message.price,
                quantity=message.quantity,
            )
            return self._build_responses(trades, timestamp)

        if isinstance(message, CancelMessage):
            self.order_book.cancel_order(message.order_id)
            return []

        return []

    def _build_responses(self, trades: List[Trade], timestamp: float) -> List[Message]:
        responses: List[Message] = []
        for trade in trades:
            self.last_price = trade.price
            responses.append(
                TradeMessage(
                    sender_id=self.exchange_id,
                    recipient_id=trade.buyer_agent_id,
                    price=trade.price,
                    quantity=trade.quantity,
                    buyer_id=trade.buyer_agent_id,
                    seller_id=trade.seller_agent_id,
                    timestamp=timestamp,
                )
            )
            responses.append(
                TradeMessage(
                    sender_id=self.exchange_id,
                    recipient_id=trade.seller_agent_id,
                    price=trade.price,
                    quantity=trade.quantity,
                    buyer_id=trade.buyer_agent_id,
                    seller_id=trade.seller_agent_id,
                    timestamp=timestamp,
                )
            )

        mid = self.order_book.mid_price or self.last_price
        responses.append(
            MarketDataMessage(
                sender_id=self.exchange_id,
                mid_price=mid,
                best_bid=self.order_book.best_bid,
                best_ask=self.order_book.best_ask,
                spread=self.order_book.spread,
                timestamp=timestamp,
            )
        )
        return responses
