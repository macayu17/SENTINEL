"""ABIDES-style order book wrapper built on SENTINEL matching engine."""

from __future__ import annotations

from typing import List, Dict

from ..market.order import Order, OrderSide, OrderType
from ..market.order_book import OrderBook
from ..market.trade import Trade


class AbidesOrderBook:
    def __init__(self) -> None:
        self._book = OrderBook()

    def add_order(self, agent_id: str, side: OrderSide, order_type: OrderType, price: float, quantity: int) -> List[Trade]:
        order = Order(agent_id=agent_id, side=side, order_type=order_type, price=price, quantity=quantity)
        return self._book.add_order(order)

    def cancel_order(self, order_id: str) -> bool:
        return self._book.cancel_order(order_id)

    def get_depth(self, levels: int = 5) -> dict[str, list]:
        return self._book.get_depth(levels)

    def get_total_depth(self, levels: int = 5) -> int:
        return self._book.get_total_depth(levels)

    def get_levels(self, levels: int = 10) -> tuple[list[dict], list[dict]]:
        depth = self._book.get_depth(levels)
        return depth.get("bids", []), depth.get("asks", [])

    @property
    def bid_levels(self) -> list[dict]:
        return self.get_levels(10)[0]

    @property
    def ask_levels(self) -> list[dict]:
        return self.get_levels(10)[1]

    def get_depth(self, levels: int = 5) -> Dict[str, list]:
        return self._book.get_depth(levels)

    def get_total_depth(self, levels: int = 5) -> int:
        return self._book.get_total_depth(levels)

    @property
    def bid_levels(self) -> list:
        return self._book.get_depth(10)["bids"]

    @property
    def ask_levels(self) -> list:
        return self._book.get_depth(10)["asks"]

    @property
    def best_bid(self) -> float | None:
        return self._book.best_bid

    @property
    def best_ask(self) -> float | None:
        return self._book.best_ask

    @property
    def mid_price(self) -> float | None:
        return self._book.mid_price

    @property
    def spread(self) -> float | None:
        return self._book.spread
