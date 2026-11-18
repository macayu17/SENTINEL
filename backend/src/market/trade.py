"""Trade data structure for the SENTINEL market simulator."""

from dataclasses import dataclass, field
from itertools import count
import time

_trade_ids = count(1)


@dataclass
class Trade:
    """Represents an executed trade between two orders."""

    buyer_order_id: str
    seller_order_id: str
    buyer_agent_id: str
    seller_agent_id: str
    price: float
    quantity: int
    taker_agent_id: str = ""  # aggressor; the other side rested and earns the maker rate
    trade_id: str = field(default_factory=lambda: f"T{next(_trade_ids)}")
    timestamp: float = field(default_factory=time.time)

    @property
    def value(self) -> float:
        """Notional value of the trade."""
        return self.price * self.quantity

    def __repr__(self) -> str:
        return (
            f"Trade({self.quantity}@{self.price:.2f} "
            f"buyer={self.buyer_agent_id} seller={self.seller_agent_id})"
        )
