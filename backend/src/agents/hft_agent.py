"""HFT agent — sub-second microstructure scalper that stays close to flat."""

from typing import List, Dict, Optional
from .base_agent import BaseAgent
from .risk import TICK, AgentRiskProfile
from ..market.order import Order, OrderSide, OrderType


class HFTAgent(BaseAgent):
    """
    Passive market maker that leans on the touch imbalance. When one side of
    the book is much thinner, the microprice sits near it and the next mid move
    is predictable, so the agent quotes only the favoured side (improving a
    wide spread by a tick, joining a tight one) and earns the maker rebate.

    It never crosses to enter: in this market the move after a queue clears is
    usually one tick, which a taker fee and half-spread eat. Positions are held
    for seconds with a passive exit at the far touch; it crosses only to cut a
    loss (tick stop), a clearly reversed signal, or a stale position.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 5_000_000.0,
        position_limit: int = 1000,
        signal_threshold: float = 0.5,
        reversal_threshold: float = 0.95,
        stop_ticks: int = 5,
        max_hold_seconds: float = 90.0,
    ) -> None:
        super().__init__(agent_id, "HFT", initial_capital)
        self.wakeup_interval = 0.2
        self.position_limit = position_limit
        self.signal_threshold = signal_threshold
        self.reversal_threshold = reversal_threshold
        self.stop_ticks = stop_ticks
        self.max_hold_seconds = max_hold_seconds
        self._entry_time: Optional[float] = None
        self.risk_profile = AgentRiskProfile(
            max_inventory=position_limit,
            base_order_size=120,
            min_order_size=10,
            participation_rate=0.04,
            max_active_orders=2,
            stale_ticks=1,
        )

    def _signal(self, market_state: Dict) -> float:
        """Microprice offset from mid in half-spreads: +1 means it sits on the ask."""
        half = max(TICK / 2, float(market_state.get("spread") or TICK) / 2)
        return (self._microprice(market_state) - self._mid(market_state)) / half

    @staticmethod
    def _passive_price(market_state: Dict, side: OrderSide) -> float:
        """Join a one-tick touch, or improve a wider one by a tick (never crossing)."""
        best_bid, best_ask = market_state.get("best_bid"), market_state.get("best_ask")
        mid = BaseAgent._mid(market_state)
        if best_bid is None or best_ask is None:
            best_bid, best_ask = mid - TICK, mid + TICK
        improve = TICK if best_ask - best_bid > TICK + 1e-9 else 0.0
        return round(best_bid + improve if side == OrderSide.BUY else best_ask - improve, 2)

    def _must_exit(self, market_state: Dict, signal: float) -> bool:
        if self.position == 0:
            return False
        sign = 1 if self.position > 0 else -1
        pnl_ticks = sign * (self._mid(market_state) - self.avg_entry_price) / TICK
        held = float(market_state.get("current_time", 0.0)) - (self._entry_time or 0.0)
        return (
            pnl_ticks <= -self.stop_ticks
            or held >= self.max_hold_seconds
            or sign * signal <= -self.reversal_threshold
        )

    def decide_action(self, market_state: Dict) -> List[Order]:
        closing = self._close_out(market_state)
        if closing is not None:
            return closing
        now = float(market_state.get("current_time", 0.0))
        signal = self._signal(market_state)

        if self.position != 0:
            if self._entry_time is None:
                self._entry_time = now
            if self._must_exit(market_state, signal):
                order = self._exit_order(market_state, self._mid(market_state), aggression=2.0)
                return [order] if order is not None else []
            if self.active_orders:
                return []
            side = OrderSide.SELL if self.position > 0 else OrderSide.BUY
            return [Order(
                agent_id=self.agent_id,
                side=side,
                order_type=OrderType.POST_ONLY,
                price=self._passive_price(market_state, side),
                quantity=abs(self.position),
            )]

        self._entry_time = None
        if self.active_orders or abs(signal) < self.signal_threshold:
            return []
        side = OrderSide.BUY if signal > 0 else OrderSide.SELL
        order = self._entry_order(
            market_state, side, OrderType.POST_ONLY, self._passive_price(market_state, side), aggression=0.6
        )
        return [order] if order is not None else []

    def cancel_for_state(self, market_state: Dict) -> List[str]:
        """Pull resting quotes once the touch moves away or the signal no longer backs them."""
        if not self.active_orders:
            return []
        signal = self._signal(market_state)
        if self.position == 0:
            backed = all(
                (signal if order.side == OrderSide.BUY else -signal) >= self.signal_threshold
                for order in self.active_orders.values()
            )
        else:
            backed = not self._must_exit(market_state, signal)
        stale = self.risk_profile.should_reprice(
            self.active_orders,
            target_bid=self._passive_price(market_state, OrderSide.BUY),
            target_ask=self._passive_price(market_state, OrderSide.SELL),
        )
        return self.cancel_all_active_orders() if stale or not backed else []

    def reset(self) -> None:
        super().reset()
        self._entry_time = None
