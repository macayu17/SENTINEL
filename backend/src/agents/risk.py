"""Shared risk and sizing helpers for synthetic trading agents."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Mapping

from ..market.order import Order, OrderSide, OrderType


@dataclass(frozen=True)
class AgentRiskProfile:
    """Small reusable profile for inventory, participation, and sizing limits."""

    max_inventory: int
    base_order_size: int
    min_order_size: int = 1
    participation_rate: float = 0.10
    max_active_orders: int = 6
    stale_ticks: int = 3

    def inventory_ratio(self, position: int) -> float:
        if self.max_inventory <= 0:
            return 0.0
        return min(1.0, abs(position) / float(self.max_inventory))

    def remaining_capacity(self, side: OrderSide, position: int) -> int:
        if self.max_inventory <= 0:
            return max(0, self.base_order_size)
        if side == OrderSide.BUY:
            return max(0, self.max_inventory - position)
        return max(0, self.max_inventory + position)

    def target_size(
        self,
        *,
        side: OrderSide,
        position: int,
        available_depth: float,
        volatility: float,
        aggression: float = 1.0,
    ) -> int:
        """Return a realistic child-order size bounded by risk and displayed depth."""
        capacity = self.remaining_capacity(side, position)
        if capacity <= 0:
            return 0

        depth_cap = int(max(1.0, available_depth) * _clamp(self.participation_rate, 0.01, 1.0))
        inventory_factor = max(0.10, 1.0 - self.inventory_ratio(position))
        vol = max(0.0, float(volatility or 0.0))
        vol_factor = 1.0 if vol <= 0.001 else 1.0 / (1.0 + 20.0 * vol)
        raw_size = self.base_order_size * inventory_factor * vol_factor * _clamp(aggression, 0.05, 2.0)
        bounded = min(capacity, depth_cap, int(max(self.min_order_size, raw_size)))
        return max(0, bounded)

    def should_reprice(
        self,
        active_orders: Mapping[str, Order],
        *,
        target_bid: float,
        target_ask: float,
        tick_size: float = 0.01,
    ) -> bool:
        """Return True when resting quotes are too stale or too numerous."""
        if len(active_orders) > self.max_active_orders:
            return True
        stale_distance = max(1, self.stale_ticks) * max(0.0001, tick_size)
        for order in active_orders.values():
            target = target_bid if order.side == OrderSide.BUY else target_ask
            if math.isfinite(order.price) and abs(order.price - target) > stale_distance:
                return True
        return False


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, float(value)))


def displayed_depth_for_side(market_state: Mapping, side: OrderSide) -> float:
    """Depth available on the side an aggressive child order would consume."""
    key = "ask_depth" if side == OrderSide.BUY else "bid_depth"
    fallback = market_state.get("total_depth", 1_000) or 1_000
    try:
        return max(1.0, float(market_state.get(key, fallback) or fallback))
    except (TypeError, ValueError):
        return 1_000.0


def passive_depth_for_side(market_state: Mapping, side: OrderSide) -> float:
    """Depth already resting on the same side as a passive quote."""
    key = "bid_depth" if side == OrderSide.BUY else "ask_depth"
    fallback = market_state.get("total_depth", 1_000) or 1_000
    try:
        return max(1.0, float(market_state.get(key, fallback) or fallback))
    except (TypeError, ValueError):
        return 1_000.0


def risk_limited_order(
    profile: AgentRiskProfile,
    *,
    agent_id: str,
    side: OrderSide,
    order_type: OrderType,
    price: float,
    position: int,
    market_state: Mapping,
    volatility: float,
    aggression: float = 1.0,
    quantity_cap: int | None = None,
    depth_fn: Callable[[Mapping, OrderSide], float] = displayed_depth_for_side,
) -> Order | None:
    """Build a profile-sized order, or return None when risk leaves no size."""
    quantity = profile.target_size(
        side=side,
        position=position,
        available_depth=depth_fn(market_state, side),
        volatility=volatility,
        aggression=aggression,
    )
    if quantity_cap is not None:
        quantity = min(quantity, max(0, int(quantity_cap)))
    if quantity <= 0:
        return None
    return Order(
        agent_id=agent_id,
        side=side,
        order_type=order_type,
        price=price,
        quantity=quantity,
    )


def near_touch_price(mid: float, side: OrderSide, spread: float, *, ticks: int = 1) -> float:
    tick = 0.01
    half = max(tick, float(spread or tick) / 2)
    offset = half + max(0, ticks - 1) * tick
    return round(mid - offset if side == OrderSide.BUY else mid + offset, 2)
