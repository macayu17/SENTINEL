"""Spoofing agent — manipulates order book with large phantom orders."""

from typing import List, Dict, Optional
import random
from .base_agent import BaseAgent
from ..market.order import Order, OrderSide, OrderType


class SpoofingAgent(BaseAgent):
    """
    Places large spoof orders a few ticks from the best bid/ask to create
    the illusion of depth, then cancels them and trades in the opposite
    direction with a smaller real order.

    Lifecycle:
    1. IDLE → wait for cooldown, then pick a side to spoof
    2. SPOOFING → place large phantom order, count down steps
    3. TRADING → cancel spoof (by not resubmitting), place real trade opposite
    4. COOLDOWN → wait before next cycle
    """

    # States
    IDLE = "idle"
    SPOOFING = "spoofing"
    TRADING = "trading"
    COOLDOWN = "cooldown"

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 10_000_000.0,
        spoof_size_min: int = 2000,
        spoof_size_max: int = 5000,
        real_order_size: int = 300,
        spoof_ticks_offset: int = 4,
        spoof_duration_steps: int = 10,
        cooldown_min: int = 50,
        cooldown_max: int = 100,
        position_limit: int = 2000,
    ) -> None:
        super().__init__(agent_id, "Spoofing", initial_capital, latency_seconds=0.0005)
        self.spoof_size_min = spoof_size_min
        self.spoof_size_max = spoof_size_max
        self.real_order_size = real_order_size
        self.spoof_ticks_offset = spoof_ticks_offset
        self.spoof_duration_steps = spoof_duration_steps
        self.cooldown_min = cooldown_min
        self.cooldown_max = cooldown_max
        self.position_limit = position_limit

        # Internal state
        self._state: str = self.IDLE
        self._spoof_side: Optional[OrderSide] = None
        self._steps_in_state: int = 0
        self._cooldown_target: int = 0

    def decide_action(self, market_state: Dict) -> List[Order]:
        price = market_state.get("mid_price") or market_state.get("current_price", 100.0)
        orders: List[Order] = []
        self._steps_in_state += 1

        # ── Flatten if over position limit ──────────────────────────────
        if abs(self.position) >= self.position_limit:
            side = OrderSide.SELL if self.position > 0 else OrderSide.BUY
            orders.append(
                Order(
                    agent_id=self.agent_id,
                    side=side,
                    order_type=OrderType.MARKET,
                    price=price,
                    quantity=min(self.real_order_size, abs(self.position)),
                )
            )
            return orders

        # ── State machine ───────────────────────────────────────────────
        if self._state == self.IDLE:
            # Pick a side and transition to spoofing
            self._spoof_side = random.choice([OrderSide.BUY, OrderSide.SELL])
            self._state = self.SPOOFING
            self._steps_in_state = 0

        if self._state == self.SPOOFING:
            # Place a large phantom order away from best price
            tick = 0.01
            spoof_size = random.randint(self.spoof_size_min, self.spoof_size_max)

            if self._spoof_side == OrderSide.BUY:
                # Large bid a few ticks below — fake buy support
                spoof_price = round(price - self.spoof_ticks_offset * tick, 2)
            else:
                # Large ask a few ticks above — fake sell pressure
                spoof_price = round(price + self.spoof_ticks_offset * tick, 2)

            orders.append(
                Order(
                    agent_id=self.agent_id,
                    side=self._spoof_side,
                    order_type=OrderType.LIMIT,
                    price=spoof_price,
                    quantity=spoof_size,
                )
            )

            # After enough steps, move to trading phase
            if self._steps_in_state >= self.spoof_duration_steps:
                self._state = self.TRADING
                self._steps_in_state = 0

        elif self._state == self.TRADING:
            # Trade in the OPPOSITE direction of the spoof
            real_side = OrderSide.SELL if self._spoof_side == OrderSide.BUY else OrderSide.BUY
            orders.append(
                Order(
                    agent_id=self.agent_id,
                    side=real_side,
                    order_type=OrderType.MARKET,
                    price=price,
                    quantity=self.real_order_size,
                )
            )
            # Enter cooldown
            self._state = self.COOLDOWN
            self._steps_in_state = 0
            self._cooldown_target = random.randint(self.cooldown_min, self.cooldown_max)

        elif self._state == self.COOLDOWN:
            if self._steps_in_state >= self._cooldown_target:
                self._state = self.IDLE
                self._steps_in_state = 0

        return orders
