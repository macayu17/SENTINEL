"""HFT agent — high-frequency mean-reversion and short-term momentum."""

from typing import List, Dict
from collections import deque
from .base_agent import BaseAgent
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

    def decide_action(self, market_state: Dict) -> List[Order]:
        price = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        imbalance = market_state.get("order_book_imbalance", 0.0)
        spread = market_state.get("spread", 0.05)
        self._price_history.append(price)
        orders: List[Order] = []

        if len(self._price_history) < 20:
            return orders

        prices = list(self._price_history)
        mean = sum(prices) / len(prices)
        std = (sum((p - mean) ** 2 for p in prices) / len(prices)) ** 0.5
        z_score = (price - mean) / std if std > 0 else 0.0

        momentum = (price - prices[-5]) / prices[-5] if len(prices) >= 5 else 0.0

        if z_score > self.z_threshold and self.position > -self.position_limit:
            qty = min(200, self.position_limit + self.position)
            if qty > 0:
                orders.append(
                    Order(
                        agent_id=self.agent_id,
                        side=OrderSide.SELL,
                        order_type=OrderType.LIMIT,
                        price=round(price + 0.01, 2),
                        quantity=qty,
                    )
                )
        elif z_score < -self.z_threshold and self.position < self.position_limit:
            qty = min(200, self.position_limit - self.position)
            if qty > 0:
                orders.append(
                    Order(
                        agent_id=self.agent_id,
                        side=OrderSide.BUY,
                        order_type=OrderType.LIMIT,
                        price=round(price - 0.01, 2),
                        quantity=qty,
                    )
                )

        if abs(momentum) > self.momentum_threshold:
            side = OrderSide.BUY if momentum > 0 else OrderSide.SELL
            if (side == OrderSide.BUY and self.position < self.position_limit) or (
                side == OrderSide.SELL and self.position > -self.position_limit
            ):
                orders.append(
                    Order(
                        agent_id=self.agent_id,
                        side=side,
                        order_type=OrderType.MARKET,
                        price=price,
                        quantity=50,
                    )
                )

        if abs(imbalance) > 0.65 and self.position != 0:
            exit_side = OrderSide.SELL if self.position > 0 else OrderSide.BUY
            orders.append(
                Order(
                    agent_id=self.agent_id,
                    side=exit_side,
                    order_type=OrderType.MARKET,
                    price=price,
                    quantity=abs(self.position),
                )
            )
            return orders

        if spread >= 0.04:
            orders.append(
                Order(
                    agent_id=self.agent_id,
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    price=round(price + 0.01, 2),
                    quantity=50,
                )
            )
            orders.append(
                Order(
                    agent_id=self.agent_id,
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    price=round(price - 0.01, 2),
                    quantity=50,
                )
            )

        return orders
