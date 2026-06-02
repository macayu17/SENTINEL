"""Retail agent — trades on moving average crossover with stop-loss/take-profit."""

from typing import List, Dict
from collections import deque
from .base_agent import BaseAgent
from .risk import AgentRiskProfile, risk_limited_exit_order, risk_limited_order
from ..market.order import Order, OrderSide, OrderType


class RetailAgent(BaseAgent):
    """
    Uses 20/50 moving average crossover for entry signals.
    Manages risk with stop-loss and take-profit thresholds.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 50_000.0,
        stop_loss: float = 0.02,
        take_profit: float = 0.05,
        order_size: int = 50,
    ) -> None:
        super().__init__(agent_id, "Retail", initial_capital, latency_seconds=0.1)
        self.wakeup_interval = 2.0
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.order_size = order_size
        self._price_history: deque = deque(maxlen=60)
        self._entry_price: float = 0.0
        self.risk_profile = AgentRiskProfile(
            max_inventory=max(500, order_size * 10),
            base_order_size=order_size,
            min_order_size=max(1, order_size // 5),
            participation_rate=0.02,
            max_active_orders=1,
            stale_ticks=5,
        )

    def decide_action(self, market_state: Dict) -> List[Order]:
        price = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        volatility = float(market_state.get("volatility", 0.0) or 0.0)
        self._price_history.append(price)
        orders: List[Order] = []

        if len(self._price_history) < 50:
            return orders

        prices = list(self._price_history)

        # Moving averages
        ma20 = sum(prices[-20:]) / 20
        ma50 = sum(prices[-50:]) / 50

        # Check stop-loss / take-profit on existing position
        if self.position != 0 and self._entry_price > 0:
            pnl_pct = (price - self._entry_price) / self._entry_price
            if self.position < 0:
                pnl_pct = -pnl_pct

            if pnl_pct <= -self.stop_loss or pnl_pct >= self.take_profit:
                # Close position
                order = risk_limited_exit_order(
                    self.risk_profile,
                    agent_id=self.agent_id,
                    position=self.position,
                    price=price,
                    market_state=market_state,
                    volatility=volatility,
                    aggression=1.2,
                )
                if order is not None:
                    orders.append(order)
                self._entry_price = 0.0
                return orders

        # MA crossover signals (only if no position)
        if self.position == 0:
            prev_ma20 = sum(prices[-21:-1]) / 20
            prev_ma50 = sum(prices[-51:-1]) / 50

            # Bullish crossover
            if prev_ma20 <= prev_ma50 and ma20 > ma50:
                order = risk_limited_order(
                    self.risk_profile,
                    agent_id=self.agent_id,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    price=price,
                    position=self.position,
                    market_state=market_state,
                    volatility=volatility,
                    active_orders=self.active_orders,
                    aggression=0.7,
                )
                if order is None:
                    return orders
                orders.append(order)
                self._entry_price = price

            # Bearish crossover
            elif prev_ma20 >= prev_ma50 and ma20 < ma50:
                order = risk_limited_order(
                    self.risk_profile,
                    agent_id=self.agent_id,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    price=price,
                    position=self.position,
                    market_state=market_state,
                    volatility=volatility,
                    active_orders=self.active_orders,
                    aggression=0.7,
                )
                if order is None:
                    return orders
                orders.append(order)
                self._entry_price = price

        return orders

    def reset(self) -> None:
        super().reset()
        self._price_history.clear()
        self._entry_price = 0.0
