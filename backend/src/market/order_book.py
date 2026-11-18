"""Order book with price-time priority matching engine."""

import bisect
import math
from typing import List, Optional, Dict
from .order import Order, OrderSide, OrderType, OrderStatus
from .trade import Trade

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
        self._depth_cache: Dict[int, Dict[str, list]] = {}

    def add_order(self, order: Order) -> List[Trade]:
        """Add an order to the book. Returns list of trades if matched."""
        if order.order_type == OrderType.POST_ONLY and self._would_cross(order):
            order.status = OrderStatus.CANCELLED  # maker-only: never pay the spread
            return []
        self._depth_cache.clear()
        is_buy = order.side == OrderSide.BUY
        book = self.asks if is_buy else self.bids

        if order.order_type == OrderType.MARKET:
            limit = self._protection_limit(order, book)
        else:
            limit = order.price
        trades = self._sweep(order, book, limit)

        if order.remaining_quantity > 0:
            if order.order_type in (OrderType.MARKET, OrderType.IOC):
                order.status = OrderStatus.CANCELLED  # never rests
            else:
                self._insert(order)
        return trades

    def accept_without_matching(self, order: Order) -> None:
        """Pre-open: orders accumulate and may cross. Nothing executes until uncrossing."""
        self._depth_cache.clear()
        self._insert(order)

    def _would_cross(self, order: Order) -> bool:
        """True if this limit price would take liquidity instead of posting."""
        if order.side == OrderSide.BUY:
            return self.best_ask is not None and order.price >= self.best_ask
        return self.best_bid is not None and order.price <= self.best_bid

    def _sweep(self, order: Order, book: List[Order], limit: Optional[float]) -> List[Trade]:
        """Take resting liquidity at prices no worse than `limit` (None = unbounded)."""
        trades: List[Trade] = []
        is_buy = order.side == OrderSide.BUY
        while order.remaining_quantity > 0 and book:
            best = book[0]
            if limit is not None and (best.price > limit if is_buy else best.price < limit):
                break
            if self._cancel_self_trade(order, book):
                continue
            fill_qty = min(order.remaining_quantity, best.remaining_quantity)
            buy, sell = (order, best) if is_buy else (best, order)
            trades.append(self._create_trade(buy, sell, best.price, fill_qty, taker_agent_id=order.agent_id))
            if best.is_filled:
                book.pop(0)
        return trades

    @staticmethod
    def _cancel_self_trade(order: Order, book: List[Order]) -> bool:
        """Self-trade prevention: cancel the resting order if the aggressor owns it."""
        resting = book[0]
        # SEED is venue bootstrap liquidity, not a participant, so it is exempt.
        if resting.agent_id != order.agent_id or resting.agent_id == "SEED":
            return False
        resting.status = OrderStatus.CANCELLED
        book.pop(0)
        return True

    @staticmethod
    def _protection_limit(order: Order, book: List[Order]) -> Optional[float]:
        """Worst price a market order may print from its observed reference or touch."""
        if not book:
            return None
        has_reference = math.isfinite(order.price) and order.price > 0
        reference = order.price if has_reference else book[0].price
        protection_pct = (
            MARKET_ORDER_REFERENCE_PROTECTION_PCT
            if has_reference
            else MARKET_ORDER_PROTECTION_PCT
        )
        band = protection_pct * abs(reference)
        return reference + band if order.side == OrderSide.BUY else reference - band

    @staticmethod
    def _create_trade(
        buy_order: Order,
        sell_order: Order,
        price: float,
        quantity: int,
        taker_agent_id: str,
    ) -> Trade:
        """Create a trade and fill both orders."""
        buy_order.fill(quantity)
        sell_order.fill(quantity)
        return Trade(
            buyer_order_id=buy_order.order_id,
            seller_order_id=sell_order.order_id,
            buyer_agent_id=buy_order.agent_id,
            seller_agent_id=sell_order.agent_id,
            price=price,
            quantity=quantity,
            taker_agent_id=taker_agent_id,
        )

    def _insert(self, order: Order) -> None:
        """Insert behind every order at the same or better price (price-time priority)."""
        if order.side == OrderSide.BUY:
            bisect.insort(self.bids, order, key=lambda resting: -resting.price)
        else:
            bisect.insort(self.asks, order, key=lambda resting: resting.price)

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

        self._depth_cache.clear()
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
                # Auctions have no aggressor, so neither side pays the taker fee.
                trades.append(self._create_trade(bid, ask, best_price, fill, taker_agent_id))
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
                    self._depth_cache.clear()
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
        cached = self._depth_cache.get(levels)
        if cached is not None:
            return cached
        bid_levels = self._aggregate_levels(self.bids, levels)
        ask_levels = self._aggregate_levels(self.asks, levels)
        depth = {"bids": bid_levels, "asks": ask_levels}
        self._depth_cache[levels] = depth
        return depth

    def get_total_depth(self, levels: int = 5) -> int:
        """Total quantity across top N levels on both sides."""
        return self._total_depth(self.bids, levels) + self._total_depth(self.asks, levels)

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

    def __repr__(self) -> str:
        return (
            f"OrderBook(bids={len(self.bids)}, asks={len(self.asks)}, "
            f"spread={self.spread})"
        )
