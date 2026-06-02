"""HFT agent — high-frequency mean-reversion and short-term momentum."""

from typing import List, Dict
from collections import deque
from .base_agent import BaseAgent
from .risk import AgentRiskProfile, near_touch_price, risk_limited_order
from ..market.order import Order, OrderSide, OrderType


class HFTAgent(BaseAgent):
    """
    Uses z-score of recent prices for mean-reversion signals
    and short-term momentum for trend-following.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 5_000_000.0,
        position_limit: int = 1000,
        lookback: int = 100,
        z_threshold: float = 2.0,
        momentum_threshold: float = 0.001,
    ) -> None:
        super().__init__(agent_id, "HFT", initial_capital, latency_seconds=0.0001)
        self.wakeup_interval = 0.2
        self.position_limit = position_limit
        self.lookback = lookback
        self.z_threshold = z_threshold
        self.momentum_threshold = momentum_threshold
        self._price_history: deque = deque(maxlen=lookback)
        self.risk_profile = AgentRiskProfile(
            max_inventory=position_limit,
            base_order_size=120,
            min_order_size=10,
            participation_rate=0.04,
            max_active_orders=3,
            stale_ticks=1,
        )

    def decide_action(self, market_state: Dict) -> List[Order]:
        price = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        imbalance = market_state.get("order_book_imbalance", 0.0)
        spread = market_state.get("spread", 0.05)
        volatility = float(market_state.get("volatility", 0.0) or 0.0)
        self._price_history.append(price)
        orders: List[Order] = []

        if self.active_orders and self._has_fresh_active_order(market_state):
            return orders

        imbalance_order = self._imbalance_scalp_order(
            price=price,
            spread=spread,
            imbalance=imbalance,
            market_state=market_state,
            volatility=volatility,
        )

        if len(self._price_history) < 20:
            return [imbalance_order] if imbalance_order is not None else orders

        # Z-score mean reversion
        prices = list(self._price_history)
        mean = sum(prices) / len(prices)
        std = (sum((p - mean) ** 2 for p in prices) / len(prices)) ** 0.5

        if std > 0:
            z_score = (price - mean) / std
        else:
            z_score = 0.0

        # Momentum (short-term return)
        momentum = (price - prices[-5]) / prices[-5] if len(prices) >= 5 else 0.0

        # Mean reversion signal
        if z_score > self.z_threshold and self.position > -self.position_limit:
            order = risk_limited_order(
                self.risk_profile,
                agent_id=self.agent_id,
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT,
                price=round(price + 0.01, 2),
                position=self.position,
                market_state=market_state,
                volatility=volatility,
                aggression=min(1.6, abs(z_score) / self.z_threshold),
            )
            if order is not None:
                orders.append(order)
        elif z_score < -self.z_threshold and self.position < self.position_limit:
            order = risk_limited_order(
                self.risk_profile,
                agent_id=self.agent_id,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                price=round(price - 0.01, 2),
                position=self.position,
                market_state=market_state,
                volatility=volatility,
                aggression=min(1.6, abs(z_score) / self.z_threshold),
            )
            if order is not None:
                orders.append(order)

        # Momentum override
        if abs(momentum) > self.momentum_threshold:
            side = OrderSide.BUY if momentum > 0 else OrderSide.SELL
            order_type = OrderType.MARKET if spread <= 0.03 and volatility < 0.04 else OrderType.LIMIT
            order = risk_limited_order(
                self.risk_profile,
                agent_id=self.agent_id,
                side=side,
                order_type=order_type,
                price=price if order_type == OrderType.MARKET else near_touch_price(price, side, spread),
                position=self.position,
                market_state=market_state,
                volatility=volatility,
                aggression=min(1.5, abs(momentum) / self.momentum_threshold),
            )
            if order is not None:
                orders.append(order)

        # Imbalance scalp: small passive quote on pressured side when spread supports it.
        if imbalance_order is not None:
            orders.append(imbalance_order)
        return orders

    def _imbalance_scalp_order(
        self,
        *,
        price: float,
        spread: float,
        imbalance: float,
        market_state: Dict,
        volatility: float,
    ) -> Order | None:
        if spread < 0.02 or abs(imbalance) <= 0.2:
            return None
        quote_side = OrderSide.BUY if imbalance > 0 else OrderSide.SELL
        quote_px = round(price - 0.01, 2) if quote_side == OrderSide.BUY else round(price + 0.01, 2)
        return risk_limited_order(
            self.risk_profile,
            agent_id=self.agent_id,
            side=quote_side,
            order_type=OrderType.LIMIT,
            price=quote_px,
            position=self.position,
            market_state=market_state,
            volatility=volatility,
            aggression=0.3,
        )

    def reset(self) -> None:
        super().reset()
        self._price_history.clear()

    def cancel_for_state(self, market_state: Dict) -> List[str]:
        if not self.active_orders:
            return []
        if self._has_fresh_active_order(market_state):
            return []
        return self.cancel_all_active_orders()

    def _has_fresh_active_order(self, market_state: Dict) -> bool:
        price = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        target_bid = round(price - 0.01, 2)
        target_ask = round(price + 0.01, 2)
        return not self.risk_profile.should_reprice(
            self.active_orders,
            target_bid=target_bid,
            target_ask=target_ask,
        )
