"""Base interfaces and shared types for live market feed adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class FeedHealth:
    connected: bool
    source: str
    provider: str
    last_update_ts: Optional[float] = None
    last_update_wall_time: Optional[float] = None
    fallback_active: bool = False
    stale: bool = False
    latency_ms: Optional[float] = None
    transport: Optional[str] = None
    message: str = ""


@dataclass
class MarketState:
    current_time: float
    current_price: float
    mid_price: float
    best_bid: float
    best_ask: float
    spread: float
    total_depth: int
    order_book_imbalance: float
    trade_flow: float
    recent_price_change: float
    recent_signed_volume: float
    time_to_close: float
    volatility: float
    step: int
    order_book_levels: Dict[str, List[Dict[str, float]]]
    recent_orders: List[Dict[str, Any]]
    recent_trades: List[Dict[str, Any]]
    recent_events: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_time": self.current_time,
            "current_price": self.current_price,
            "mid_price": self.mid_price,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "spread": self.spread,
            "total_depth": self.total_depth,
            "order_book_imbalance": self.order_book_imbalance,
            "trade_flow": self.trade_flow,
            "recent_price_change": self.recent_price_change,
            "recent_signed_volume": self.recent_signed_volume,
            "time_to_close": self.time_to_close,
            "volatility": self.volatility,
            "step": self.step,
            "order_book_levels": self.order_book_levels,
            "recent_orders": self.recent_orders,
            "recent_trades": self.recent_trades,
            "recent_events": self.recent_events,
        }


class LiveMarketFeed(ABC):
    """Adapter interface for pluggable live market data sources."""

    @abstractmethod
    async def start(self) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...

    @abstractmethod
    def latest_state(self) -> Optional[MarketState]:
        ...

    @abstractmethod
    def health(self) -> FeedHealth:
        ...
