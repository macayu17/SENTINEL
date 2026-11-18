"""Market Maker agent — provides liquidity via bid/ask quotes with inventory skew."""

from typing import List, Dict
from .base_agent import BaseAgent
from .risk import TICK, AgentRiskProfile, passive_depth_for_side
from ..market.order import Order, OrderSide, OrderType


class MarketMakerAgent(BaseAgent):
    """
    Continuously quotes a ladder of `quote_levels` bids and asks, `rung_ticks`
    apart, around an inventory-skewed reservation price, so resting depth comes
    from market makers rather than venue bootstrap orders. Re-quotes the whole
    ladder only when its top has moved or most of it has traded away.
    Stops quoting a side at 85% of max inventory and flattens near the close.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 1_000_000.0,
        base_spread: float = 0.001,
        quote_size: int = 100,
        max_inventory: int = 5000,
        quote_levels: int = 4,
        rung_ticks: int = 2,
    ) -> None:
        super().__init__(agent_id, "MarketMaker", initial_capital)
        self.base_spread = base_spread
        self.quote_size = quote_size
        self.max_inventory = max_inventory
        self.quote_levels = quote_levels
        self.rung_ticks = rung_ticks
        self._quoted: tuple[float, float] | None = None  # ladder tops when last quoted
        self.risk_profile = AgentRiskProfile(
            max_inventory=max_inventory,
            base_order_size=quote_size,
            min_order_size=max(1, quote_size // 10),
            participation_rate=0.08,
            max_active_orders=2 * quote_levels,
            stale_ticks=2,
        )

    def decide_action(self, market_state: Dict) -> List[Order]:
        time_to_close = market_state.get("time_to_close", float("inf"))
        imbalance = float(market_state.get("order_book_imbalance", 0.0) or 0.0)
        orders: List[Order] = []
        mid, bid_price, ask_price = self._quote_targets(market_state)

        # Flatten near close
        if time_to_close < 600 and self.position != 0:
            order = self._exit_order(market_state, mid, aggression=1.5)
            if order is not None:
                orders.append(order)
            return orders

        if self.active_orders and not self._ladder_stale(bid_price, ask_price):
            return orders

        # Inventory ratio determines quoting behaviour
        inv_ratio = abs(self.position) / self.max_inventory if self.max_inventory else 0

        quote_specs = [
            (OrderSide.BUY, bid_price, self.position <= 0.85 * self.max_inventory),
            (OrderSide.SELL, ask_price, self.position >= -0.85 * self.max_inventory),
        ]
        for side, price, enabled in quote_specs:
            if not enabled:
                continue
            same_side_crowding = max(0.0, imbalance if side == OrderSide.BUY else -imbalance)
            opposite_side_need = max(0.0, -imbalance if side == OrderSide.BUY else imbalance)
            queue_aggression = (0.7 if inv_ratio > 0.5 else 1.0)
            queue_aggression *= 1.0 - min(0.9, same_side_crowding * 0.95)
            queue_aggression *= 1.0 + min(0.3, opposite_side_need * 0.3)
            order = self._entry_order(
                market_state,
                side,
                OrderType.POST_ONLY,
                price,
                aggression=queue_aggression,
                depth_fn=passive_depth_for_side,
            )
            if order is None:
                continue
            # Deeper rungs at the same size, within inventory room.
            room = self.risk_profile.remaining_capacity(side, self.position, self.active_orders)
            rungs = max(1, min(self.quote_levels, room // max(1, order.quantity)))
            # Deeper rungs sit further apart: they only fill on sweeps, which tend to be informed.
            step = (-TICK if side == OrderSide.BUY else TICK) * self.rung_ticks
            orders.append(order)
            orders.extend(
                Order(self.agent_id, side, OrderType.POST_ONLY, round(price + level * step, 2), order.quantity)
                for level in range(1, rungs)
            )
        if orders:
            self._quoted = (bid_price, ask_price)
        return orders

    def _ladder_stale(self, bid_price: float, ask_price: float) -> bool:
        """Re-quote when the ladder top has moved past tolerance or most of it has traded."""
        if self._quoted is None:
            return True
        tolerance = self.risk_profile.stale_ticks * TICK + 1e-9
        moved = abs(self._quoted[0] - bid_price) > tolerance or abs(self._quoted[1] - ask_price) > tolerance
        return moved or len(self.active_orders) < self.quote_levels

    def cancel_for_state(self, market_state: Dict) -> List[str]:
        if not self.active_orders:
            return []
        time_to_close = market_state.get("time_to_close", float("inf"))
        if time_to_close < 600 and self.position != 0:
            return self.cancel_all_active_orders()
        _, bid_price, ask_price = self._quote_targets(market_state)
        return self.cancel_all_active_orders() if self._ladder_stale(bid_price, ask_price) else []

    def _quote_targets(self, market_state: Dict) -> tuple[float, float, float]:
        mid = self._mid(market_state)
        spread = float(market_state.get("spread", 0.02) or 0.02)
        volatility = float(market_state.get("volatility", 0.0) or 0.0)
        imbalance = float(market_state.get("order_book_imbalance", 0.0) or 0.0)
        # Net aggressor volume over the last 10s as a share of the visible book. One-sided
        # flow is the classic sign of informed trading, so it moves and widens the quotes.
        depth = max(1.0, float(market_state.get("total_depth") or 0.0))
        toxicity = max(-1.0, min(1.0, float(market_state.get("recent_signed_volume") or 0.0) / depth))

        vol_multiplier = 1.0 + min(4.0, volatility * 40.0)
        imbalance_multiplier = 1.0 + min(0.5, abs(imbalance) * 0.5)
        competitive_half_spread = min(
            (self.base_spread * mid) / 2,
            max(0.01, spread / 2),
        )
        half_spread = max(
            0.01,
            competitive_half_spread * vol_multiplier * imbalance_multiplier * (1.0 + 0.5 * abs(toxicity)),
        )
        inventory_skew = (self.position / self.max_inventory) * half_spread * 2 if self.max_inventory else 0.0
        # Avellaneda-Stoikov reservation price, centred on the microprice rather than the mid.
        reservation = self._microprice(market_state) + toxicity * half_spread - inventory_skew

        bid_price = round(reservation - half_spread, 2)
        ask_price = round(reservation + half_spread, 2)
        return mid, bid_price, ask_price

    def reset(self) -> None:
        super().reset()
        self._quoted = None
