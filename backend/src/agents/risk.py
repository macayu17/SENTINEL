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

    def remaining_capacity(
        self,
        side: OrderSide,
        position: int,
        active_orders: Mapping[str, Order] | None = None,
    ) -> int:
        if self.max_inventory <= 0:
            return max(0, self.base_order_size)
        pending = active_exposure_for_side(active_orders or {}, side)
        if side == OrderSide.BUY:
            return max(0, self.max_inventory - position - pending)
        return max(0, self.max_inventory + position - pending)

    def target_size(
        self,
        *,
        side: OrderSide,
        position: int,
        available_depth: float,
        volatility: float,
        active_orders: Mapping[str, Order] | None = None,
        aggression: float = 1.0,
    ) -> int:
        """Return a realistic child-order size bounded by risk and displayed depth."""
        capacity = self.remaining_capacity(side, position, active_orders=active_orders)
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


def active_exposure_for_side(active_orders: Mapping[str, Order], side: OrderSide) -> int:
    """Count resting same-side shares that still consume inventory capacity."""
    exposure = 0
    for order in active_orders.values():
        if order.side != side:
            continue
        try:
            remaining = int(order.remaining_quantity)
        except (TypeError, ValueError):
            remaining = 0
        exposure += max(0, remaining)
    return exposure


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
    active_orders: Mapping[str, Order] | None = None,
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
        active_orders=active_orders,
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


def risk_limited_exit_order(
    profile: AgentRiskProfile,
    *,
    agent_id: str,
    position: int,
    price: float,
    market_state: Mapping,
    volatility: float,
    aggression: float = 1.0,
) -> Order | None:
    """Build a reduce-only market order capped by displayed contra-side depth."""
    if position == 0:
        return None
    side = OrderSide.SELL if position > 0 else OrderSide.BUY
    available_depth = displayed_depth_for_side(market_state, side)
    depth_cap = int(max(1.0, available_depth) * _clamp(profile.participation_rate, 0.01, 1.0))
    vol = max(0.0, float(volatility or 0.0))
    vol_factor = 1.0 if vol <= 0.001 else 1.0 / (1.0 + 10.0 * vol)
    target = int(profile.base_order_size * vol_factor * _clamp(aggression, 0.05, 3.0))
    quantity = min(abs(position), max(profile.min_order_size, target), max(1, depth_cap))
    if quantity <= 0:
        return None
    return Order(
        agent_id=agent_id,
        side=side,
        order_type=OrderType.MARKET,
        price=price,
        quantity=quantity,
    )


def near_touch_price(mid: float, side: OrderSide, spread: float, *, ticks: int = 1) -> float:
    tick = 0.01
    half = max(tick, float(spread or tick) / 2)
    offset = half + max(0, ticks - 1) * tick
    return round(mid - offset if side == OrderSide.BUY else mid + offset, 2)


# ── Central rule gate ────────────────────────────────────────────────────
# Applied by the simulator to EVERY sim-mode agent order, regardless of how
# the agent built it (risk_limited_order, raw Order, RL policy, ...).
MAX_LEVERAGE = 2.0           # gross exposure ≤ 2× initial capital
MAX_DRAWDOWN_PCT = 0.25      # total PnL ≤ -25% of capital → reduce-only
PRICE_COLLAR_PCT = 0.05      # limit prices > 5% from mid are fat-fingers
CLOSE_PHASE_SIZE_FACTOR = 0.5  # de-risk: halve opening size in CLOSE phase


def enforce_trading_rules(
    agent,
    orders: list[Order],
    market_state: Mapping,
) -> tuple[list[Order], list[tuple[Order, str]]]:
    """Uniform per-agent trading rules for sim mode.

    Rules, in order per order:
      1. price collar — reject limit prices > PRICE_COLLAR_PCT from mid
      2. drawdown kill switch — latches agent.risk_halted; halted agents
         may only reduce their position
      3. CLOSE session phase — opening size is halved (uses session_phase)
      4. leverage cap — worst-case same-side exposure (position + resting
         + this batch) must stay within MAX_LEVERAGE × initial capital

    Orders are clipped when possible and rejected otherwise. Returns
    (accepted_orders, [(rejected_order, reason), ...]).
    """
    if not orders:
        return [], []
    try:
        mid = float(market_state.get("mid_price") or market_state.get("current_price") or 0.0)
    except (TypeError, ValueError):
        mid = 0.0
    if not math.isfinite(mid) or mid <= 0:
        return list(orders), []

    total_pnl = agent.realized_pnl + agent.get_unrealized_pnl(mid)
    if math.isfinite(total_pnl) and total_pnl <= -MAX_DRAWDOWN_PCT * agent.initial_capital:
        agent.risk_halted = True  # latches until reset()

    phase = market_state.get("session_phase")
    is_close = phase == "CLOSE"
    is_squareoff = phase == "SQUAREOFF"
    max_exposure = (MAX_LEVERAGE * agent.initial_capital) / mid
    collar = PRICE_COLLAR_PCT * mid

    accepted: list[Order] = []
    rejected: list[tuple[Order, str]] = []
    projected = agent.position  # folds in orders accepted earlier in this batch

    for order in orders:
        if order.order_type == OrderType.LIMIT and (
            not math.isfinite(order.price) or abs(order.price - mid) > collar
        ):
            rejected.append((order, "price_collar"))
            continue

        sign = 1 if order.side == OrderSide.BUY else -1
        quantity = max(0, int(order.quantity))
        # Split into the part that shrinks |position| and the part that opens new risk.
        reduce_part = min(quantity, max(0, -projected * sign))
        open_part = quantity - reduce_part
        blocked_reason = "leverage_cap"

        if open_part > 0:
            if agent.risk_halted or is_squareoff:
                # Reduce-only: halted books and the square-off window may not open risk.
                blocked_reason = "risk_halted" if agent.risk_halted else "squareoff"
                open_part = 0
            else:
                if is_close:
                    open_part = max(1, int(open_part * CLOSE_PHASE_SIZE_FACTOR))
                pending = active_exposure_for_side(agent.active_orders, order.side)
                headroom = int(max_exposure - max(0, projected * sign) - pending)
                open_part = min(open_part, max(0, headroom))

        quantity = reduce_part + open_part
        if quantity < 1:
            rejected.append((order, blocked_reason))
            continue

        order.quantity = quantity
        accepted.append(order)
        projected += sign * quantity

    return accepted, rejected
