"""Informed agent that trades on the simulator's optional fundamental oracle."""

from typing import List, Dict
from .base_agent import BaseAgent
from .risk import AgentRiskProfile, near_touch_price, risk_limited_exit_order, risk_limited_order
from ..market.order import Order, OrderSide, OrderType


class InformedAgent(BaseAgent):
    """
    Has a small probability each step of receiving private information.
    When informed, trades aggressively in the signal direction
    until the signal expires.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 5_000_000.0,
        signal_probability: float = 0.01,
        signal_accuracy: float = 0.70,
        signal_duration: int = 120,
        max_position: int = 5000,
    ) -> None:
        super().__init__(agent_id, "Informed", initial_capital, latency_seconds=0.005)
        self.wakeup_interval = 0.6
        self.signal_probability = signal_probability
        self.signal_accuracy = signal_accuracy
        self.signal_duration = signal_duration
        self.max_position = max_position

        self._active_signal: str | None = None  # "buy" or "sell"
        self._signal_start_time: float = 0.0
        self.risk_profile = AgentRiskProfile(
            max_inventory=max_position,
            base_order_size=500,
            min_order_size=25,
            participation_rate=0.08,
            max_active_orders=2,
            stale_ticks=3,
        )

    def decide_action(self, market_state: Dict) -> List[Order]:
        current_time = market_state.get("current_time", 0.0)
        price = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        spread = float(market_state.get("spread", 0.05) or 0.05)
        volatility = float(market_state.get("volatility", 0.0) or 0.0)
        oracle = market_state.get("oracle") or {}
        fundamental = oracle.get("fundamental_value")
        orders: List[Order] = []

        # Check if current signal has expired
        if self._active_signal and (current_time - self._signal_start_time) > self.signal_duration:
            # Unwind position
            if self.position != 0:
                order = risk_limited_exit_order(
                    self.risk_profile,
                    agent_id=self.agent_id,
                    position=self.position,
                    price=price,
                    market_state=market_state,
                    volatility=volatility,
                    aggression=1.5,
                )
                if order is not None:
                    orders.append(order)
            self._active_signal = None
            return orders

        if self._active_signal and isinstance(fundamental, (int, float)):
            gap = fundamental - price
            live_direction = "buy" if gap > 0 else "sell"
            if abs(gap) <= max(0.01, spread / 2) or live_direction != self._active_signal:
                if self.position != 0:
                    order = risk_limited_exit_order(
                        self.risk_profile,
                        agent_id=self.agent_id,
                        position=self.position,
                        price=price,
                        market_state=market_state,
                        volatility=volatility,
                        aggression=1.5,
                    )
                    if order is not None:
                        orders.append(order)
                self._active_signal = None
                return orders

        # Check for new signal
        if not self._active_signal and self.rng.random() < self.signal_probability:
            if not isinstance(fundamental, (int, float)):
                return orders
            observation_noise = max(
                0.0,
                float(oracle.get("observation_noise", 0.0) or 0.0),
            )
            observed_fundamental = fundamental + self.rng.gauss(
                0.0,
                observation_noise,
            )
            if abs(observed_fundamental - price) <= max(0.01, spread / 2):
                return orders
            direction = "buy" if observed_fundamental > price else "sell"
            self._active_signal = direction
            self._signal_start_time = current_time

        # Trade on active signal
        if self._active_signal:
            side = OrderSide.BUY if self._active_signal == "buy" else OrderSide.SELL
            current_pos = abs(self.position)

            if current_pos < self.max_position:
                order_type = OrderType.MARKET if spread <= 0.05 else OrderType.LIMIT
                order = risk_limited_order(
                    self.risk_profile,
                    agent_id=self.agent_id,
                    side=side,
                    order_type=order_type,
                    price=price if order_type == OrderType.MARKET else near_touch_price(price, side, spread),
                    position=self.position,
                    market_state=market_state,
                    volatility=volatility,
                    active_orders=self.active_orders,
                    aggression=1.3,
                )
                if order is None:
                    return orders
                orders.append(order)

        return orders

    def reset(self) -> None:
        super().reset()
        self._active_signal = None
        self._signal_start_time = 0.0
