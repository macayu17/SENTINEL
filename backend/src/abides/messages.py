"""ABIDES-style message definitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from ..market.order import OrderSide, OrderType


class MessageType(Enum):
    ORDER = auto()
    CANCEL = auto()
    MARKET_DATA = auto()
    TRADE = auto()


@dataclass
class Message:
    msg_type: MessageType
    sender_id: str
    recipient_id: Optional[str] = None
    timestamp: float = 0.0


@dataclass
class OrderMessage(Message):
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.LIMIT
    price: float = 0.0
    quantity: int = 0

    def __init__(
        self,
        sender_id: str,
        side: OrderSide,
        order_type: OrderType,
        price: float,
        quantity: int,
        timestamp: float = 0.0,
    ) -> None:
        super().__init__(MessageType.ORDER, sender_id, None, timestamp)
        self.side = side
        self.order_type = order_type
        self.price = float(price)
        self.quantity = int(quantity)


@dataclass
class CancelMessage(Message):
    order_id: str = ""

    def __init__(self, sender_id: str, order_id: str, timestamp: float = 0.0) -> None:
        super().__init__(MessageType.CANCEL, sender_id, None, timestamp)
        self.order_id = order_id


@dataclass
class MarketDataMessage(Message):
    mid_price: float = 0.0
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    spread: Optional[float] = None
    oracle: Optional[dict] = None

    def __init__(
        self,
        sender_id: str,
        mid_price: float,
        best_bid: Optional[float],
        best_ask: Optional[float],
        spread: Optional[float],
        oracle: Optional[dict] = None,
        timestamp: float = 0.0,
    ) -> None:
        super().__init__(MessageType.MARKET_DATA, sender_id, None, timestamp)
        self.mid_price = float(mid_price)
        self.best_bid = best_bid
        self.best_ask = best_ask
        self.spread = spread
        self.oracle = oracle


@dataclass
class TradeMessage(Message):
    price: float = 0.0
    quantity: int = 0
    buyer_id: str = ""
    seller_id: str = ""

    def __init__(
        self,
        sender_id: str,
        recipient_id: str,
        price: float,
        quantity: int,
        buyer_id: str,
        seller_id: str,
        timestamp: float = 0.0,
    ) -> None:
        super().__init__(MessageType.TRADE, sender_id, recipient_id, timestamp)
        self.price = float(price)
        self.quantity = int(quantity)
        self.buyer_id = buyer_id
        self.seller_id = seller_id
