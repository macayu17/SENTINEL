"""Order data structures for the SENTINEL market simulator."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid
import time


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    POST_ONLY = "post_only"  # maker-only: rejected outright if it would cross
    IOC = "ioc"              # immediate-or-cancel: fill what you can, never rest
    STOP = "stop"            # parked at the venue; becomes a market order on trigger


#: Order types that rest on the book rather than sweeping it.
RESTING_ORDER_TYPES = frozenset({OrderType.LIMIT, OrderType.POST_ONLY})


class OrderStatus(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"


@dataclass
class Order:
    """Represents a single order in the order book."""

    agent_id: str
    side: OrderSide
    order_type: OrderType
    price: float
    quantity: int
    order_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)
    filled_quantity: int = 0
    status: OrderStatus = OrderStatus.PENDING
    #: Iceberg: shares shown to the book at a time. 0 means fully displayed.
    display_quantity: int = 0
    @property
    def remaining_quantity(self) -> int:
        return self.quantity - self.filled_quantity

    @property
    def is_iceberg(self) -> bool:
        return 0 < self.display_quantity < self.quantity

    @property
    def displayed_quantity(self) -> int:
        """Shares visible in market data — the hidden remainder is not quoted."""
        if not self.is_iceberg:
            return self.remaining_quantity
        return min(self.display_quantity, self.remaining_quantity)

    @property
    def is_filled(self) -> bool:
        return self.filled_quantity >= self.quantity

    def fill(self, quantity: int) -> None:
        """Fill this order by the given quantity."""
        if quantity <= 0:
            raise ValueError(f"Fill quantity must be positive, got {quantity}")
        if quantity > self.remaining_quantity:
            raise ValueError(
                f"Cannot fill {quantity}, only {self.remaining_quantity} remaining"
            )
        self.filled_quantity += quantity
        if self.is_filled:
            self.status = OrderStatus.FILLED
        else:
            self.status = OrderStatus.PARTIAL

    def __repr__(self) -> str:
        return (
            f"Order({self.side.value} {self.order_type.value} "
            f"{self.remaining_quantity}/{self.quantity}@{self.price:.2f} "
            f"[{self.status.value}])"
        )
