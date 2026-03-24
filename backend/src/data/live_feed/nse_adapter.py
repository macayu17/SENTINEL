"""NSE-style/broker-style live feed adapter skeleton.

This is a provider skeleton meant for future broker or NSE integration.
It preserves the same LiveMarketFeed contract and normalized MarketState shape.
"""

from __future__ import annotations

from typing import Optional

from .base import FeedHealth, LiveMarketFeed, MarketState


class NseLikeLiveFeedAdapter(LiveMarketFeed):
    def __init__(
        self,
        symbol: str,
        duration_seconds: int,
        reconnect_base_delay: float = 1.0,
        reconnect_max_delay: float = 20.0,
    ) -> None:
        self.symbol = symbol
        self.duration_seconds = duration_seconds
        self.reconnect_base_delay = reconnect_base_delay
        self.reconnect_max_delay = reconnect_max_delay

        self._running = False
        self._connected = False
        self._last_update_ts: Optional[float] = None
        self._message = "not_started"

    async def start(self) -> None:
        self._running = True
        # Future implementation:
        # 1) authenticate with broker/NSE gateway
        # 2) subscribe to top-of-book depth, ticker, and trades
        # 3) normalize raw payloads via normalize.build_market_state
        self._connected = False
        self._message = "skeleton_adapter_not_implemented"

    async def stop(self) -> None:
        self._running = False
        self._connected = False

    def latest_state(self) -> Optional[MarketState]:
        # No real state yet; caller should fallback to mock provider.
        return None

    def health(self) -> FeedHealth:
        return FeedHealth(
            connected=self._connected,
            source="nse",
            provider="nse",
            last_update_ts=self._last_update_ts,
            last_update_wall_time=None,
            fallback_active=False,
            stale=True,
            latency_ms=None,
            transport="skeleton",
            message=self._message,
        )
