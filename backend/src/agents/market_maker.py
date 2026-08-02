"""Market Maker agent — provides liquidity via bid/ask quotes with inventory skew."""

from typing import List, Dict
from .base_agent import BaseAgent
from .risk import AgentRiskProfile, passive_depth_for_side, risk_limited_exit_order, risk_limited_order
from ..market.order import Order, OrderSide, OrderType


class MarketMakerAgent(BaseAgent):
    """
    Continuously quotes bid and ask around mid-price.
    Skews quotes proportionally to inventory to manage risk.
    Halves quote size at 50% max inventory, stops quoting at 90%.
    Flattens position near market close.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 1_000_000.0,
        base_spread: float = 0.001,
        quote_size: int = 100,
        max_inventory: int = 5000,
    ) -> None:
        super().__init__(agent_id, "MarketMaker", initial_capital, latency_seconds=0.001)
        self.base_spread = base_spread
        self.quote_size = quote_size
        self.max_inventory = max_inventory
        self.risk_profile = AgentRiskProfile(
            max_inventory=max_inventory,
            base_order_size=quote_size,
            min_order_size=max(1, quote_size // 10),
            participation_rate=0.08,
            max_active_orders=2,
            stale_ticks=2,
        )

    def decide_action(self, market_state: Dict) -> List[Order]:
        time_to_close = market_state.get("time_to_close", float("inf"))
        volatility = float(market_state.get("volatility", 0.0) or 0.0)
        imbalance = float(market_state.get("order_book_imbalance", 0.0) or 0.0)
        orders: List[Order] = []
        mid, bid_price, ask_price = self._quote_targets(market_state)

        # Flatten near close
        if time_to_close < 600 and self.position != 0:
            order = risk_limited_exit_order(
                self.risk_profile,
                agent_id=self.agent_id,
                position=self.position,
                price=mid,
                market_state=market_state,
                volatility=volatility,
                aggression=1.5,
            )
            if order is not None:
                orders.append(order)
            return orders

        if self.active_orders and not self.risk_profile.should_reprice(
            self.active_orders,
            target_bid=bid_price,
            target_ask=ask_price,
        ):
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
            order = risk_limited_order(
                self.risk_profile,
                agent_id=self.agent_id,
                side=side,
                # Maker-only: a quote that crosses is a spread paid, not a spread earned.
                order_type=OrderType.POST_ONLY,
                price=price,
                position=self.position,
                market_state=market_state,
                volatility=volatility,
                active_orders=self.active_orders,
                aggression=queue_aggression,
                depth_fn=passive_depth_for_side,
            )
            if order is not None:
                orders.append(order)
        return orders

    def cancel_for_state(self, market_state: Dict) -> List[str]:
        if not self.active_orders:
            return []
        time_to_close = market_state.get("time_to_close", float("inf"))
        if time_to_close < 600 and self.position != 0:
            return self.cancel_all_active_orders()
        _, bid_price, ask_price = self._quote_targets(market_state)
        if self.risk_profile.should_reprice(
            self.active_orders,
            target_bid=bid_price,
            target_ask=ask_price,
        ):
            return self.cancel_all_active_orders()
        return []

    def _quote_targets(self, market_state: Dict) -> tuple[float, float, float]:
        mid = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        spread = float(market_state.get("spread", 0.02) or 0.02)
        volatility = float(market_state.get("volatility", 0.0) or 0.0)
        imbalance = float(market_state.get("order_book_imbalance", 0.0) or 0.0)

        # Inventory and volatility widen quotes; imbalance shifts reservation price.
        vol_multiplier = 1.0 + min(4.0, volatility * 40.0)
        imbalance_multiplier = 1.0 + min(0.5, abs(imbalance) * 0.5)
        competitive_half_spread = min(
            (self.base_spread * mid) / 2,
            max(0.01, spread / 2),
        )
        half_spread = max(
            0.01,
            competitive_half_spread * vol_multiplier * imbalance_multiplier,
        )
        inventory_skew = (self.position / self.max_inventory) * half_spread * 2 if self.max_inventory else 0.0
        reservation = mid - inventory_skew

        bid_price = round(reservation - half_spread, 2)
        ask_price = round(reservation + half_spread, 2)
        return mid, bid_price, ask_price
