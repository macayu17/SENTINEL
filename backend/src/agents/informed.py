"""Informed agent that trades on a private, noisy read of the fundamental."""

from typing import List, Dict, Optional
from .base_agent import BaseAgent, TAKER_FEE_PER_SHARE
from .risk import TICK, AgentRiskProfile, near_touch_price
from ..market.order import Order, OrderSide, OrderType


class InformedAgent(BaseAgent):
    """
    Occasionally receives a private signal: one noisy look at the hidden
    fundamental. It acts only when the gap to the market beats a round trip
    (spread + fees + a tick of margin), then works toward its own estimate,
    crossing the spread when the edge is large and resting near the touch when
    it is thin. Below the hurdle it stops adding and holds; it exits once the
    price passes the estimate or the signal goes stale.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 5_000_000.0,
        signal_probability: float = 0.01,
        signal_duration: int = 120,
        max_position: int = 5000,
    ) -> None:
        super().__init__(agent_id, "Informed", initial_capital)
        self.wakeup_interval = 0.6
        self.signal_probability = signal_probability
        self.signal_duration = signal_duration
        self.max_position = max_position

        self._active_signal: str | None = None  # "buy" or "sell"
        self._estimate: Optional[float] = None
        self._signal_start_time: float = 0.0
        self.risk_profile = AgentRiskProfile(
            max_inventory=max_position,
            base_order_size=500,
            min_order_size=25,
            participation_rate=0.08,
            max_active_orders=2,
            stale_ticks=3,
        )

    @staticmethod
    def _hurdle(spread: float) -> float:
        """Edge a trade must clear: cross the spread, pay two taker fees, keep a tick."""
        return spread + 2 * TAKER_FEE_PER_SHARE + TICK

    def _drop_signal(self, market_state: Dict, price: float) -> List[Order]:
        self._active_signal = None
        self._estimate = None
        order = self._exit_order(market_state, price, aggression=1.5)
        return [order] if order is not None else []

    def decide_action(self, market_state: Dict) -> List[Order]:
        closing = self._close_out(market_state)
        if closing is not None:
            self._active_signal = self._estimate = None
            return closing
        current_time = float(market_state.get("current_time", 0.0) or 0.0)
        price = self._mid(market_state)
        spread = float(market_state.get("spread", 0.05) or 0.05)
        oracle = market_state.get("oracle") or {}
        fundamental = oracle.get("fundamental_value")

        if (
            self._estimate is None
            and isinstance(fundamental, (int, float))
            and self.rng.random() < self.signal_probability
        ):
            noise = max(0.0, float(oracle.get("observation_noise", 0.0) or 0.0))
            estimate = fundamental + self.rng.gauss(0.0, noise)
            if abs(estimate - price) > self._hurdle(spread):
                self._estimate = estimate
                self._active_signal = "buy" if estimate > price else "sell"
                self._signal_start_time = current_time

        if self._estimate is None:
            return self._drop_signal(market_state, price)  # no live signal: flatten leftovers
        direction = 1 if self._active_signal == "buy" else -1
        edge = direction * (self._estimate - price)
        if current_time - self._signal_start_time > self.signal_duration or edge <= 0:
            return self._drop_signal(market_state, price)  # stale, or the price got there
        hurdle = self._hurdle(spread)
        if edge < hurdle:
            # Our own buying ate the edge. That impact is temporary: hold for the
            # information to reach the price instead of selling back into it.
            return []

        side = OrderSide.BUY if direction > 0 else OrderSide.SELL
        # Kyle-style intensity: trade harder the larger the remaining mispricing.
        aggression = max(0.5, min(2.0, edge / hurdle))
        if edge >= 2 * hurdle:
            order = self._entry_order(market_state, side, OrderType.MARKET, price, aggression=aggression)
        else:
            order = self._entry_order(
                market_state, side, OrderType.LIMIT, near_touch_price(price, side, spread), aggression=aggression
            )
        return [order] if order is not None else []

    def reset(self) -> None:
        super().reset()
        self._active_signal = None
        self._estimate = None
        self._signal_start_time = 0.0

    def cancel_for_state(self, market_state: Dict) -> List[str]:
        if not self.active_orders:
            return []
        current_time = float(market_state.get("current_time", 0.0) or 0.0)
        if (
            not self._active_signal
            or current_time - self._signal_start_time > self.signal_duration
        ):
            return self.cancel_all_active_orders()
        price = self._mid(market_state)
        spread = float(market_state.get("spread", 0.05) or 0.05)
        side = OrderSide.BUY if self._active_signal == "buy" else OrderSide.SELL
        target = near_touch_price(price, side, spread)
        if self.risk_profile.should_reprice(
            self.active_orders,
            target_bid=target if side == OrderSide.BUY else price,
            target_ask=target if side == OrderSide.SELL else price,
        ):
            return self.cancel_all_active_orders()
        return []
