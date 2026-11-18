"""Mean Reversion agent — Bollinger Band + RSI contrarian strategy."""

from typing import List, Dict
from collections import deque
import math
from .base_agent import BaseAgent
from .risk import AgentRiskProfile
from ..market.order import Order, OrderSide, OrderType


class MeanReversionAgent(BaseAgent):
    """
    Buys when price touches the lower Bollinger Band with RSI < 30.
    Sells when price touches the upper Bollinger Band with RSI > 70.
    Exits when price returns to the moving average, or stops out once price runs
    `stop_std` band-widths past entry — the reversion thesis has failed.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 3_000_000.0,
        lookback: int = 30,
        num_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        position_limit: int = 2000,
        order_size: int = 150,
        stop_std: float = 2.0,
    ) -> None:
        super().__init__(agent_id, "MeanReversion", initial_capital)
        self.lookback = lookback
        self.num_std = num_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.position_limit = position_limit
        self.order_size = order_size
        self.stop_std = stop_std
        self._stop_price: float | None = None
        self._price_history: deque = deque(maxlen=max(lookback, rsi_period + 1) + 10)
        self.risk_profile = AgentRiskProfile(
            max_inventory=position_limit,
            base_order_size=order_size,
            min_order_size=max(10, order_size // 10),
            participation_rate=0.05,
            max_active_orders=2,
            stale_ticks=4,
        )

    def _compute_rsi(self, prices: List[float]) -> float:
        """Compute RSI from a price series."""
        if len(prices) < self.rsi_period + 1:
            return 50.0  # neutral default

        changes = [prices[i] - prices[i - 1] for i in range(-self.rsi_period, 0)]
        gains = [c for c in changes if c > 0]
        losses = [-c for c in changes if c < 0]

        avg_gain = sum(gains) / self.rsi_period if gains else 0.0
        avg_loss = sum(losses) / self.rsi_period if losses else 0.0

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def decide_action(self, market_state: Dict) -> List[Order]:
        price = self._mid(market_state)
        self._price_history.append(price)
        orders: List[Order] = []
        closing = self._close_out(market_state)
        if closing is not None:
            return closing

        if len(self._price_history) < self.lookback:
            return orders

        prices = list(self._price_history)

        # Bollinger Bands
        window = prices[-self.lookback:]
        sma = sum(window) / len(window)
        variance = sum((p - sma) ** 2 for p in window) / len(window)
        std = math.sqrt(variance) if variance > 0 else 0.0

        upper_band = sma + self.num_std * std
        lower_band = sma - self.num_std * std

        # RSI
        rsi = self._compute_rsi(prices)

        # ── Manage existing position: exit at the mean, or stop out ─────
        if self.position == 0:
            self._stop_price = None
        else:
            sign = 1 if self.position > 0 else -1
            if self._stop_price is None:
                self._stop_price = self.avg_entry_price - sign * self.stop_std * max(std, 0.01)
            if sign * (price - sma) >= 0 or sign * (price - self._stop_price) <= 0:
                order = self._exit_order(market_state, price, aggression=1.2)
                if order is not None:
                    orders.append(order)
            return orders

        # ── Entry signals (only if flat) ────────────────────────────────
        if self.position == 0 and std > 0:
            # Buy at lower band with oversold RSI
            if price <= lower_band and rsi < self.rsi_oversold:
                order = self._entry_order(
                    market_state,
                    OrderSide.BUY,
                    OrderType.LIMIT,
                    round(price + 0.01, 2),
                    aggression=0.9,
                )
                if order is None:
                    return orders
                orders.append(order)

            # Sell at upper band with overbought RSI
            elif price >= upper_band and rsi > self.rsi_overbought:
                order = self._entry_order(
                    market_state,
                    OrderSide.SELL,
                    OrderType.LIMIT,
                    round(price - 0.01, 2),
                    aggression=0.9,
                )
                if order is None:
                    return orders
                orders.append(order)

        return orders

    def reset(self) -> None:
        super().reset()
        self._price_history.clear()
        self._stop_price = None

    def cancel_for_state(self, market_state: Dict) -> List[str]:
        if not self.active_orders:
            return []
        price = self._mid(market_state)
        target_bid = round(price + 0.01, 2)
        target_ask = round(price - 0.01, 2)
        if self.risk_profile.should_reprice(
            self.active_orders,
            target_bid=target_bid,
            target_ask=target_ask,
        ):
            return self.cancel_all_active_orders()
        return []
