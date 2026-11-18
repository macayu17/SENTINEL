"""Momentum agent — trend-following with breakout channels and trailing stop."""

from typing import List, Dict
from collections import deque
from .base_agent import BaseAgent
from .risk import AgentRiskProfile
from ..market.order import Order, OrderSide, OrderType


class MomentumAgent(BaseAgent):
    """
    Tracks an N-bar high/low price channel.
    Enters on a breakout above the channel high (below the low) only when the
    last 10s of aggressor flow agrees: a breakout nobody is buying is a fakeout.
    Exits on a trailing stop or when the breakout fails back through mid-channel.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 2_000_000.0,
        channel_length: int = 50,
        position_limit: int = 3000,
        trailing_stop_pct: float = 0.015,
        order_size: int = 200,
    ) -> None:
        super().__init__(agent_id, "Momentum", initial_capital)
        self.channel_length = channel_length
        self.position_limit = position_limit
        self.trailing_stop_pct = trailing_stop_pct
        self.order_size = order_size
        self._price_history: deque = deque(maxlen=channel_length + 1)  # channel + current
        self._peak_price: float = 0.0  # tracks high-water mark for trailing stop
        self._trough_price: float = float("inf")  # tracks low-water mark for short trailing stop
        self.risk_profile = AgentRiskProfile(
            max_inventory=position_limit,
            base_order_size=order_size,
            min_order_size=max(10, order_size // 10),
            participation_rate=0.05,
            max_active_orders=2,
            stale_ticks=3,
        )

    def decide_action(self, market_state: Dict) -> List[Order]:
        price = self._mid(market_state)
        self._price_history.append(price)
        orders: List[Order] = []
        closing = self._close_out(market_state)
        if closing is not None:
            return closing

        if len(self._price_history) <= self.channel_length:
            return orders

        previous = list(self._price_history)[:-1]
        channel_high, channel_low = max(previous), min(previous)
        channel_mid = (channel_high + channel_low) / 2

        if self.position != 0:
            # Exit on the trailing stop, or once the breakout fails back past mid-channel.
            # (Exiting on re-entry into the channel would fire on the very next tick,
            # because the entry print itself becomes the new channel high/low.)
            is_long = self.position > 0
            if is_long:
                self._peak_price = max(self._peak_price, price)
                adverse_move = (self._peak_price - price) / self._peak_price
                failed = price < channel_mid
            else:
                self._trough_price = min(self._trough_price, price)
                adverse_move = (price - self._trough_price) / self._trough_price
                failed = price > channel_mid
            if adverse_move >= self.trailing_stop_pct or failed:
                order = self._exit_order(market_state, price, aggression=1.3)
                if order is not None:
                    orders.append(order)
            return orders

        flow = float(market_state.get("recent_signed_volume") or 0.0)
        if (price > channel_high and flow > 0) or (price < channel_low and flow < 0):
            side = OrderSide.BUY if price > channel_high else OrderSide.SELL
            order = self._entry_order(market_state, side, OrderType.MARKET, price, aggression=1.2)
            if order is not None:
                orders.append(order)
                self._peak_price = self._trough_price = price
        return orders

    def reset(self) -> None:
        super().reset()
        self._price_history.clear()
        self._peak_price = 0.0
        self._trough_price = float("inf")
