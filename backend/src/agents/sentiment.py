"""Sentiment agent — herding/contrarian based on simulated market sentiment."""

from typing import List, Dict
from collections import deque
from .base_agent import BaseAgent
from .risk import AgentRiskProfile, near_touch_price, risk_limited_order
from ..market.order import Order, OrderSide, OrderType


class SentimentAgent(BaseAgent):
    """
    Simulates crowd-driven trading behaviour.
    In 'herding' mode (default 70%), follows the recent price trend.
    In 'contrarian' mode (30%), trades against it.
    Sentiment regime flips randomly with a small probability each step.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 500_000.0,
        lookback: int = 20,
        position_limit: int = 1000,
        order_size: int = 80,
        herding_probability: float = 0.70,
        regime_switch_prob: float = 0.02,
        action_probability: float = 0.15,
    ) -> None:
        super().__init__(agent_id, "Sentiment", initial_capital, latency_seconds=0.05)
        self.lookback = lookback
        self.position_limit = position_limit
        self.order_size = order_size
        self.herding_probability = herding_probability
        self.regime_switch_prob = regime_switch_prob
        self.action_probability = action_probability
        self._price_history: deque = deque(maxlen=lookback + 5)

        # Start in herding or contrarian mode randomly
        self._is_herding: bool = self.rng.random() < herding_probability
        self.risk_profile = AgentRiskProfile(
            max_inventory=position_limit,
            base_order_size=order_size,
            min_order_size=max(5, order_size // 8),
            participation_rate=0.03,
            max_active_orders=2,
            stale_ticks=5,
        )

    def decide_action(self, market_state: Dict) -> List[Order]:
        price = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        spread = float(market_state.get("spread", 0.05) or 0.05)
        volatility = float(market_state.get("volatility", 0.0) or 0.0)
        self._price_history.append(price)
        orders: List[Order] = []

        if len(self._price_history) < self.lookback:
            return orders

        # ── Regime switching ────────────────────────────────────────────
        if self.rng.random() < self.regime_switch_prob:
            self._is_herding = not self._is_herding

        # ── Only act with some probability (not every step) ─────────────
        if self.rng.random() > self.action_probability:
            return orders

        # ── Determine recent trend ──────────────────────────────────────
        prices = list(self._price_history)
        recent_return = (prices[-1] - prices[-self.lookback]) / prices[-self.lookback]

        # Dead zone: no signal if trend is negligible
        if abs(recent_return) < 0.0005:
            return orders

        trend_is_up = recent_return > 0

        # ── Decide trade direction ──────────────────────────────────────
        if self._is_herding:
            # Follow the trend
            want_buy = trend_is_up
        else:
            # Go against the trend
            want_buy = not trend_is_up

        # ── Place order if within limits ────────────────────────────────
        if want_buy and self.position < self.position_limit:
            order_type = OrderType.MARKET if spread <= 0.04 else OrderType.LIMIT
            order = risk_limited_order(
                self.risk_profile,
                agent_id=self.agent_id,
                side=OrderSide.BUY,
                order_type=order_type,
                price=price if order_type == OrderType.MARKET else near_touch_price(price, OrderSide.BUY, spread),
                position=self.position,
                market_state=market_state,
                volatility=volatility,
                active_orders=self.active_orders,
                aggression=0.8,
            )
            if order is not None:
                orders.append(order)

        elif not want_buy and self.position > -self.position_limit:
            order_type = OrderType.MARKET if spread <= 0.04 else OrderType.LIMIT
            order = risk_limited_order(
                self.risk_profile,
                agent_id=self.agent_id,
                side=OrderSide.SELL,
                order_type=order_type,
                price=price if order_type == OrderType.MARKET else near_touch_price(price, OrderSide.SELL, spread),
                position=self.position,
                market_state=market_state,
                volatility=volatility,
                active_orders=self.active_orders,
                aggression=0.8,
            )
            if order is not None:
                orders.append(order)

        return orders

    def reset(self) -> None:
        super().reset()
        self._price_history.clear()
        self._is_herding = self.rng.random() < self.herding_probability

    def cancel_for_state(self, market_state: Dict) -> List[str]:
        if not self.active_orders:
            return []
        price = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        spread = float(market_state.get("spread", 0.05) or 0.05)
        if self.risk_profile.should_reprice(
            self.active_orders,
            target_bid=near_touch_price(price, OrderSide.BUY, spread),
            target_ask=near_touch_price(price, OrderSide.SELL, spread),
        ):
            return self.cancel_all_active_orders()
        return []
