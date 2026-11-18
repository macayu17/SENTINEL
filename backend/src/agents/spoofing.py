"""Spoofing agent — manipulates order book with large phantom orders."""

from typing import List, Dict, Optional
from .base_agent import BaseAgent
from .risk import TICK, AgentRiskProfile
from ..market.order import Order, OrderSide, OrderType


class SpoofingAgent(BaseAgent):
    """
    Places large spoof orders a few ticks from the best bid/ask to create
    the illusion of depth, then cancels them and trades in the opposite
    direction with a smaller real order.

    Lifecycle:
    1. IDLE → wait for cooldown, then pick a side to spoof
    2. SPOOFING → place large phantom order, count down steps
    3. TRADING → spoof already cancelled; place the real trade opposite
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
        super().__init__(agent_id, "Spoofing", initial_capital)
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
        self._spoof_order_id: Optional[str] = None
        self._pending_cancellations: List[str] = []
        self.risk_profile = AgentRiskProfile(
            max_inventory=position_limit,
            base_order_size=real_order_size,
            min_order_size=max(10, real_order_size // 10),
            participation_rate=0.06,
            max_active_orders=1,
            stale_ticks=1,
        )

    def decide_action(self, market_state: Dict) -> List[Order]:
        price = self._mid(market_state)
        orders: List[Order] = []
        self._steps_in_state += 1

        closing = self._close_out(market_state)
        if closing is not None:
            if self._spoof_order_id is not None:
                self._pending_cancellations.append(self._spoof_order_id)
                self._spoof_order_id = None
            return closing

        # ── Flatten if over position limit ──────────────────────────────
        if abs(self.position) >= self.position_limit:
            order = self._exit_order(market_state, price, aggression=1.5)
            if order is not None:
                orders.append(order)
            return orders

        # ── State machine ───────────────────────────────────────────────
        if self._state == self.IDLE:
            # Pick a side and transition to spoofing
            self._spoof_side = self.rng.choice([OrderSide.BUY, OrderSide.SELL])
            self._state = self.SPOOFING
            self._steps_in_state = 0

        if self._state == self.SPOOFING:
            if self._spoof_order_id is None:
                # Place one large phantom order away from best price.
                spoof_size = self.rng.randint(self.spoof_size_min, self.spoof_size_max)

                if self._spoof_side == OrderSide.BUY:
                    spoof_price = round(price - self.spoof_ticks_offset * TICK, 2)
                else:
                    spoof_price = round(price + self.spoof_ticks_offset * TICK, 2)

                spoof_order = Order(
                    agent_id=self.agent_id,
                    side=self._spoof_side,
                    order_type=OrderType.LIMIT,
                    price=spoof_price,
                    quantity=spoof_size,
                )
                self._spoof_order_id = spoof_order.order_id
                orders.append(spoof_order)

            # After enough steps, pull the phantom order. Cancels are processed at the
            # start of the next wakeup, so the layer is gone before the real trade lands.
            if self._steps_in_state >= self.spoof_duration_steps:
                if self._spoof_order_id is not None:
                    self._pending_cancellations.append(self._spoof_order_id)
                    self._spoof_order_id = None
                self._state = self.TRADING
                self._steps_in_state = 0

        elif self._state == self.TRADING:
            # Trade in the OPPOSITE direction of the spoof
            real_side = OrderSide.SELL if self._spoof_side == OrderSide.BUY else OrderSide.BUY
            order = self._entry_order(
                market_state,
                real_side,
                OrderType.MARKET,
                price,
                aggression=1.2,
            )
            if order is None:
                return orders
            orders.append(order)
            # Enter cooldown
            self._state = self.COOLDOWN
            self._steps_in_state = 0
            self._cooldown_target = self.rng.randint(self.cooldown_min, self.cooldown_max)

        elif self._state == self.COOLDOWN:
            if self._steps_in_state >= self._cooldown_target:
                self._state = self.IDLE
                self._steps_in_state = 0

        return orders

    def consume_cancellations(self) -> List[str]:
        cancellations = self._pending_cancellations[:]
        self._pending_cancellations.clear()
        return cancellations

    def reset(self) -> None:
        super().reset()
        self._state = self.IDLE
        self._spoof_side = None
        self._steps_in_state = 0
        self._cooldown_target = 0
        self._spoof_order_id = None
        self._pending_cancellations.clear()
