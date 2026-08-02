"""Order book with price-time priority matching engine."""

import math
from typing import List, Optional, Dict
from .order import Order, OrderSide, OrderType, OrderStatus
from .trade import Trade
from ..utils.logger import get_logger

logger = get_logger("order_book")

# Pseudo-agents that own bootstrap/venue liquidity — not real participants, so exempt from STP.
STP_EXEMPT_AGENTS = frozenset({"SEED", "EXTERNAL_DEPTH"})

# Exchange market-order protection: a sweep stops this far from the touch it arrived at.
MARKET_ORDER_PROTECTION_PCT = 0.02
# Orders generated from an observed mid use a tighter collar around that reference.
MARKET_ORDER_REFERENCE_PROTECTION_PCT = 0.005


class OrderBook:
    """
    Limit order book with price-time priority matching.

    Bids are sorted descending by price (best bid first).
    Asks are sorted ascending by price (best ask first).
    Within the same price level, earlier orders have priority.
    """

    def __init__(self) -> None:
        self.bids: List[Order] = []
        self.asks: List[Order] = []
        self.trades: List[Trade] = []
        self._trade_count: int = 0

    def add_order(self, order: Order) -> List[Trade]:
        """Add an order to the book. Returns list of trades if matched."""
        if order.order_type == OrderType.MARKET:
            return self._match_market_order(order)
        if order.order_type == OrderType.POST_ONLY and self._would_cross(order):
            order.status = OrderStatus.CANCELLED  # maker-only: never pay the spread
            return []
        return self._match_limit_order(order)

    def accept_without_matching(self, order: Order) -> None:
        """Pre-open: orders accumulate and may cross. Nothing executes until uncrossing."""
        if order.side == OrderSide.BUY:
            self._insert_bid(order)
        else:
            self._insert_ask(order)

    def _would_cross(self, order: Order) -> bool:
        """True if this limit price would take liquidity instead of posting."""
        if order.side == OrderSide.BUY:
            return self.best_ask is not None and order.price >= self.best_ask
        return self.best_bid is not None and order.price <= self.best_bid

    def _match_market_order(self, order: Order) -> List[Trade]:
        """Match a market order against the opposite side, within the protection band."""
        trades: List[Trade] = []
        book = self.asks if order.side == OrderSide.BUY else self.bids
        limit = self._protection_limit(order, book)

        while order.remaining_quantity > 0 and book:
            if self._cancel_self_trade(order, book):
                continue
            best = book[0]
            if limit is not None and (
                best.price > limit if order.side == OrderSide.BUY else best.price < limit
            ):
                break  # sweep would print outside the band — leave the rest unfilled
            fill_qty = min(order.remaining_quantity, best.remaining_quantity)
            if order.side == OrderSide.BUY:
                trade = self._create_trade(order, best, best.price, fill_qty, taker=order)
            else:
                trade = self._create_trade(best, order, best.price, fill_qty, taker=order)
            trades.append(trade)

            if best.is_filled:
                book.pop(0)

        if order.remaining_quantity > 0:
            order.status = OrderStatus.CANCELLED  # unfilled market order remainder

        return trades

    def _match_limit_order(self, order: Order) -> List[Trade]:
        """Match a limit order, then rest any unfilled quantity on the book."""
        trades: List[Trade] = []

        if order.side == OrderSide.BUY:
            # Match against asks where ask price <= order price
            while (
                order.remaining_quantity > 0
                and self.asks
                and self.asks[0].price <= order.price
            ):
                if self._cancel_self_trade(order, self.asks):
                    continue
                best_ask = self.asks[0]
                fill_qty = min(order.remaining_quantity, best_ask.remaining_quantity)
                trade = self._create_trade(order, best_ask, best_ask.price, fill_qty, taker=order)
                trades.append(trade)
                if best_ask.is_filled:
                    self.asks.pop(0)

            # Rest unfilled quantity on the bid side
            if order.remaining_quantity > 0:
                self._rest_or_cancel(order, self._insert_bid)

        else:  # SELL
            # Match against bids where bid price >= order price
            while (
                order.remaining_quantity > 0
                and self.bids
                and self.bids[0].price >= order.price
            ):
                if self._cancel_self_trade(order, self.bids):
                    continue
                best_bid = self.bids[0]
                fill_qty = min(order.remaining_quantity, best_bid.remaining_quantity)
                trade = self._create_trade(best_bid, order, best_bid.price, fill_qty, taker=order)
                trades.append(trade)
                if best_bid.is_filled:
                    self.bids.pop(0)

            # Rest unfilled quantity on the ask side
            if order.remaining_quantity > 0:
                self._rest_or_cancel(order, self._insert_ask)

        return trades

    @staticmethod
    def _rest_or_cancel(order: Order, insert) -> None:
        """Post the remainder, unless the order is not allowed to rest."""
        if order.order_type == OrderType.IOC:
            order.status = OrderStatus.CANCELLED
            return
        insert(order)

    @staticmethod
    def _cancel_self_trade(order: Order, book: List[Order]) -> bool:
        """Self-trade prevention: cancel the resting order if the aggressor owns it."""
        resting = book[0]
        if resting.agent_id != order.agent_id or resting.agent_id in STP_EXEMPT_AGENTS:
            return False
        resting.status = OrderStatus.CANCELLED
        book.pop(0)
        return True

    @staticmethod
    def _protection_limit(order: Order, book: List[Order]) -> Optional[float]:
        """Worst price a market order may print from its observed reference or touch."""
        if not book:
            return None
        touch = book[0].price
        has_reference = math.isfinite(order.price) and order.price > 0
        reference = order.price if has_reference else touch
        protection_pct = (
            MARKET_ORDER_REFERENCE_PROTECTION_PCT
            if has_reference
            else MARKET_ORDER_PROTECTION_PCT
        )
        band = protection_pct * abs(reference)
        return reference + band if order.side == OrderSide.BUY else reference - band

    def _create_trade(
        self,
        buy_order: Order,
        sell_order: Order,
        price: float,
        quantity: int,
        taker: Optional[Order] = None,
    ) -> Trade:
        """Create a trade and fill both orders. `taker` is the aggressing side."""
        buy_order.fill(quantity)
        sell_order.fill(quantity)
        self._trade_count += 1

        trade = Trade(
            buyer_order_id=buy_order.order_id,
            seller_order_id=sell_order.order_id,
            buyer_agent_id=buy_order.agent_id,
            seller_agent_id=sell_order.agent_id,
            price=price,
            quantity=quantity,
            taker_agent_id=(taker or buy_order).agent_id,
        )
        self.trades.append(trade)
        return trade

    def _insert_bid(self, order: Order) -> None:
        """Insert a bid order in descending price order (price-time priority)."""
        for i, existing in enumerate(self.bids):
            if order.price > existing.price:
                self.bids.insert(i, order)
                return
        self.bids.append(order)

    def _insert_ask(self, order: Order) -> None:
        """Insert an ask order in ascending price order (price-time priority)."""
        for i, existing in enumerate(self.asks):
            if order.price < existing.price:
                self.asks.insert(i, order)
                return
        self.asks.append(order)

    def uncross_auction(self, taker_agent_id: str = "AUCTION") -> tuple[Optional[float], List[Trade]]:
        """Clear the book at a single uniform price, as an opening/closing auction does.

        The clearing price is the one that matches the most volume; ties break to
        the price closest to the current mid, matching NSE/NYSE equilibrium rules.
        Returns (clearing_price, trades).
        """
        if not self.bids or not self.asks or self.bids[0].price < self.asks[0].price:
            return None, []  # book is not crossed, nothing to uncross

        candidates = sorted({order.price for order in self.bids + self.asks})
        reference = self.mid_price or candidates[len(candidates) // 2]

        best_price, best_volume = None, 0
        for price in candidates:
            demand = sum(o.remaining_quantity for o in self.bids if o.price >= price)
            supply = sum(o.remaining_quantity for o in self.asks if o.price <= price)
            matched = min(demand, supply)
            if matched > best_volume or (
                matched == best_volume
                and matched > 0
                and abs(price - reference) < abs(best_price - reference)
            ):
                best_price, best_volume = price, matched

        if not best_volume or best_price is None:
            return None, []

        # Everyone who qualifies trades at the single clearing price, in book order.
        eligible_bids = [o for o in self.bids if o.price >= best_price]
        eligible_asks = [o for o in self.asks if o.price <= best_price]
        trades: List[Trade] = []
        remaining = best_volume
        ask_index = 0
        for bid in eligible_bids:
            while remaining > 0 and bid.remaining_quantity > 0 and ask_index < len(eligible_asks):
                ask = eligible_asks[ask_index]
                if ask.remaining_quantity == 0:
                    ask_index += 1
                    continue
                fill = min(bid.remaining_quantity, ask.remaining_quantity, remaining)
                if fill <= 0:
                    break
                trades.append(self._create_trade(bid, ask, best_price, fill, taker=None))
                trades[-1].taker_agent_id = taker_agent_id  # auctions have no aggressor
                remaining -= fill
            if remaining <= 0:
                break

        self.bids = [o for o in self.bids if o.remaining_quantity > 0]
        self.asks = [o for o in self.asks if o.remaining_quantity > 0]
        return best_price, trades

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order by ID. Returns True if found and cancelled."""
        for book in (self.bids, self.asks):
            for i, order in enumerate(book):
                if order.order_id == order_id:
                    order.status = OrderStatus.CANCELLED
                    book.pop(i)
                    return True
        return False

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> Optional[float]:
        if self.best_bid is not None and self.best_ask is not None:
            return (self.best_bid + self.best_ask) / 2
        return None

    @property
    def spread(self) -> Optional[float]:
        if self.best_bid is not None and self.best_ask is not None:
            return self.best_ask - self.best_bid
        return None

    def get_depth(self, levels: int = 5) -> Dict[str, list]:
        """Get order book depth for the top N price levels."""
        bid_levels = self._aggregate_levels(self.bids, levels)
        ask_levels = self._aggregate_levels(self.asks, levels)
        return {"bids": bid_levels, "asks": ask_levels}

    def get_total_depth(self, levels: int = 5) -> int:
        """Total quantity across top N levels on both sides."""
        return self._total_depth(self.bids, levels) + self._total_depth(self.asks, levels)

    def replace_depth(
        self,
        bids: List[Dict[str, float]],
        asks: List[Dict[str, float]],
        agent_id: str = "EXTERNAL_DEPTH",
    ) -> None:
        """Replace the book with already-aggregated market-depth levels."""
        self.bids = [
            self._depth_level_to_order(level, OrderSide.BUY, agent_id)
            for level in bids
            if self._valid_depth_level(level)
        ]
        self.asks = [
            self._depth_level_to_order(level, OrderSide.SELL, agent_id)
            for level in asks
            if self._valid_depth_level(level)
        ]
        self.bids.sort(key=lambda order: order.price, reverse=True)
        self.asks.sort(key=lambda order: order.price)

    def _aggregate_levels(
        self, orders: List[Order], levels: int
    ) -> List[Dict[str, float]]:
        """Aggregate orders into price levels."""
        level_map = self._aggregate_level_sizes(orders, levels)
        return [
            {"price": price, "size": size} for price, size in level_map.items()
        ]

    @staticmethod
    def _aggregate_level_sizes(orders: List[Order], levels: int) -> Dict[float, int]:
        """Aggregate visible size only — iceberg reserve is not quoted.

        ponytail: the hidden remainder still matches at full size and keeps its
        time priority. Real venues make an iceberg lose priority each time its
        display slice refreshes; add that if queue dynamics start to matter.
        """
        level_map: Dict[float, int] = {}
        for order in orders:
            price = round(order.price, 2)
            level_map[price] = level_map.get(price, 0) + order.displayed_quantity
            if len(level_map) >= levels:
                break
        return level_map

    @classmethod
    def _total_depth(cls, orders: List[Order], levels: int) -> int:
        return sum(cls._aggregate_level_sizes(orders, levels).values())

    @staticmethod
    def _valid_depth_level(level: Dict[str, float]) -> bool:
        try:
            price = float(level.get("price"))
            size = int(float(level.get("size")))
        except (TypeError, ValueError):
            return False
        return math.isfinite(price) and price > 0 and size > 0

    @staticmethod
    def _depth_level_to_order(
        level: Dict[str, float],
        side: OrderSide,
        agent_id: str,
    ) -> Order:
        return Order(
            agent_id=agent_id,
            side=side,
            order_type=OrderType.LIMIT,
            price=round(float(level["price"]), 2),
            quantity=max(1, int(float(level["size"]))),
        )

    def __repr__(self) -> str:
        return (
            f"OrderBook(bids={len(self.bids)}, asks={len(self.asks)}, "
            f"trades={self._trade_count}, spread={self.spread})"
        )
