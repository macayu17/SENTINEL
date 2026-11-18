"""Abstract base agent for the SENTINEL market simulator."""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import math
import random
from ..market.order import Order, OrderSide, OrderType
from ..market.trade import Trade
from .risk import AgentRiskProfile, displayed_depth_for_side, risk_limited_exit_order, risk_limited_order

# Generic NASDAQ maker-taker research assumptions, in USD per share.
TAKER_FEE_PER_SHARE = 0.003
MAKER_REBATE_PER_SHARE = 0.002
MAX_TAKER_FEE_NOTIONAL_PCT = 0.01


class BaseAgent(ABC):
    """
    Abstract base class for all trading agents.

    Every agent has capital, a position, and tracks its own PnL.
    Subclasses must implement decide_action() to produce orders
    based on the current market state.
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        initial_capital: float = 100_000.0,
    ) -> None:
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.cash = initial_capital

        # Position tracking
        self.position: int = 0  # net shares held (positive=long, negative=short)
        self.avg_entry_price: float = 0.0
        self.realized_pnl: float = 0.0
        self.fees_paid: float = 0.0
        self.num_trades: int = 0
        self.active_orders: Dict[str, Order] = {}
        self.risk_halted: bool = False  # latched by the sim rule gate on max drawdown
        # Subclasses replace this; the default has no inventory limit.
        self.risk_profile = AgentRiskProfile(max_inventory=0, base_order_size=1)
        self._random_seed: int | None = None
        self.rng = random.Random()

    def set_random_seed(self, seed: int) -> None:
        """Give this agent an independent reproducible random stream."""
        self._random_seed = int(seed)
        self.rng.seed(self._random_seed)

    @abstractmethod
    def decide_action(self, market_state: Dict) -> List[Order]:
        """
        Given the current market state, return a list of orders to submit.
        Must be implemented by every agent subclass.
        """
        ...

    @staticmethod
    def _mid(market_state: Dict) -> float:
        return market_state.get("mid_price") or market_state.get("current_price", 100.0)

    @classmethod
    def _microprice(cls, market_state: Dict) -> float:
        """Touch prices weighted by the opposite queue: leans toward the side about to deplete."""
        bids, asks = market_state.get("bid_levels"), market_state.get("ask_levels")
        if not bids or not asks:
            return cls._mid(market_state)
        bid, ask = bids[0], asks[0]
        total = bid["size"] + ask["size"]
        if total <= 0:
            return cls._mid(market_state)
        return (bid["price"] * ask["size"] + ask["price"] * bid["size"]) / total

    def _close_out(self, market_state: Dict) -> Optional[List[Order]]:
        """Speculative books open nothing once the close starts and work their risk down.

        Returns None outside the closing phases, so callers fall through to normal logic.
        """
        if market_state.get("session_phase") not in ("CLOSE", "SQUAREOFF"):
            return None
        order = self._exit_order(market_state, self._mid(market_state), aggression=1.5)
        return [order] if order is not None else []

    def _entry_order(
        self,
        market_state: Dict,
        side: OrderSide,
        order_type: OrderType,
        price: float,
        *,
        aggression: float = 1.0,
        quantity_cap: Optional[int] = None,
        depth_fn=displayed_depth_for_side,
    ) -> Optional[Order]:
        """A risk-profile-sized order that opens or adds to a position, or None if no size is left."""
        return risk_limited_order(
            self.risk_profile,
            agent_id=self.agent_id,
            side=side,
            order_type=order_type,
            price=price,
            position=self.position,
            market_state=market_state,
            volatility=float(market_state.get("volatility", 0.0) or 0.0),
            active_orders=self.active_orders,
            aggression=aggression,
            quantity_cap=quantity_cap,
            depth_fn=depth_fn,
        )

    def _exit_order(self, market_state: Dict, price: float, *, aggression: float = 1.0) -> Optional[Order]:
        """A reduce-only market order working the current position down, or None if flat."""
        return risk_limited_exit_order(
            self.risk_profile,
            agent_id=self.agent_id,
            position=self.position,
            price=price,
            market_state=market_state,
            volatility=float(market_state.get("volatility", 0.0) or 0.0),
            aggression=aggression,
        )

    def consume_cancellations(self) -> List[str]:
        """Return any outstanding order IDs the simulator should cancel."""
        return []

    def cancel_for_state(self, market_state: Dict) -> List[str]:
        """Return cancellations that depend on the current market snapshot."""
        return self.consume_cancellations()

    def cancel_all_active_orders(self) -> List[str]:
        """Cancel and clear any currently tracked resting orders."""
        order_ids = list(self.active_orders.keys())
        self.active_orders.clear()
        return order_ids

    def update_position(self, trade: Trade) -> None:
        """Update position and PnL after a trade fills."""
        if trade.buyer_agent_id == self.agent_id:
            self._apply_fill(trade.quantity, trade.price, is_buy=True)
        elif trade.seller_agent_id == self.agent_id:
            self._apply_fill(trade.quantity, trade.price, is_buy=False)
        self._charge_fee(trade)
        self.num_trades += 1

    def _charge_fee(self, trade: Trade) -> None:
        """Apply a simple maker rebate or taker fee for this fill."""
        if trade.taker_agent_id == self.agent_id:
            fee = min(
                trade.quantity * TAKER_FEE_PER_SHARE,
                trade.value * MAX_TAKER_FEE_NOTIONAL_PCT,
            )
        else:
            fee = -trade.quantity * MAKER_REBATE_PER_SHARE

        if not math.isfinite(fee):
            return
        self.fees_paid += fee
        self.cash -= fee
        self.realized_pnl -= fee

    def _apply_fill(self, quantity: int, price: float, is_buy: bool) -> None:
        """Apply a fill to the position, tracking average entry and realized PnL."""
        if not math.isfinite(price):
            return

        direction = 1 if is_buy else -1
        new_qty = direction * quantity
        cash_delta = price * quantity

        if is_buy:
            self.cash -= cash_delta
        else:
            self.cash += cash_delta

        if (self.position >= 0 and is_buy) or (self.position <= 0 and not is_buy):
            # Adding to position: update average entry
            total_cost = self.avg_entry_price * abs(self.position) + price * quantity
            self.position += new_qty
            if self.position != 0:
                self.avg_entry_price = total_cost / abs(self.position)
        else:
            # Reducing or flipping position: realize PnL
            close_qty = min(quantity, abs(self.position))
            if is_buy:
                pnl = (self.avg_entry_price - price) * close_qty  # closing short
            else:
                pnl = (price - self.avg_entry_price) * close_qty  # closing long
            self.realized_pnl += pnl
            self.position += new_qty

            # If flipped, the remainder is a new position at the trade price
            if abs(new_qty) > close_qty:
                self.avg_entry_price = price

    def reset(self) -> None:
        """Reset mutable state for a fresh simulation episode."""
        if self._random_seed is not None:
            self.rng.seed(self._random_seed)
        self.capital = self.initial_capital
        self.cash = self.initial_capital
        self.position = 0
        self.avg_entry_price = 0.0
        self.realized_pnl = 0.0
        self.fees_paid = 0.0
        self.num_trades = 0
        self.active_orders.clear()
        self.risk_halted = False

    def get_unrealized_pnl(self, current_price: float) -> float:
        """Mark-to-market unrealized PnL."""
        if self.position == 0:
            return 0.0
        if not math.isfinite(current_price) or not math.isfinite(self.avg_entry_price):
            return 0.0
        return (current_price - self.avg_entry_price) * self.position

    def get_metrics(self, current_price: float = 0.0) -> Dict:
        """Return agent performance metrics."""
        realized = self.realized_pnl if math.isfinite(self.realized_pnl) else 0.0
        unrealized = self.get_unrealized_pnl(current_price)
        if not math.isfinite(unrealized):
            unrealized = 0.0
        total_pnl = realized + unrealized
        if not math.isfinite(total_pnl):
            total_pnl = 0.0
        return_pct = (total_pnl / self.initial_capital) * 100 if self.initial_capital else 0.0
        if not math.isfinite(return_pct):
            return_pct = 0.0

        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "position": self.position,
            "total_pnl": round(total_pnl, 2),
            "realized_pnl": round(realized, 2),
            "unrealized_pnl": round(unrealized, 2),
            "return_pct": round(return_pct, 4),
            "num_trades": self.num_trades,
            "fees_paid": round(self.fees_paid, 2),
            "halted": self.risk_halted,
        }

    def __repr__(self) -> str:
        return f"{self.agent_type}({self.agent_id}, pos={self.position}, pnl={self.realized_pnl:.2f})"
