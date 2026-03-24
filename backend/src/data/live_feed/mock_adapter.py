"""Fallback mock live-feed adapter used when real exchange data is unavailable."""

from __future__ import annotations

import random
import time
from collections import deque
from typing import Optional, Dict, Any, List

from .base import LiveMarketFeed, MarketState, FeedHealth
from .normalize import build_market_state


class MockLiveFeedAdapter(LiveMarketFeed):
    def __init__(self, initial_price: float, duration_seconds: int) -> None:
        self.initial_price = initial_price
        self.duration_seconds = duration_seconds
        self._step = 0
        self._last_state: Optional[MarketState] = None
        self._running = False
        self._last_update_ts: Optional[float] = None
        self._last_update_wall_time: Optional[float] = None

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    def _build_next(self) -> MarketState:
        self._step += 1
        base_mid = self._last_state.mid_price if self._last_state else self.initial_price
        mid = max(1.0, base_mid + (random.random() - 0.5) * 0.25)
        spread = max(0.01, min(0.18, (self._last_state.spread if self._last_state else 0.06) + (random.random() - 0.5) * 0.01))

        best_bid = round(mid - spread / 2, 3)
        best_ask = round(mid + spread / 2, 3)

        bids: List[Dict[str, float]] = []
        asks: List[Dict[str, float]] = []
        total_depth = 0
        for level in range(10):
            bid_px = round(best_bid - level * 0.01, 3)
            ask_px = round(best_ask + level * 0.01, 3)
            bid_sz = int(max(20, 220 / (level + 1) + random.uniform(-25, 25)))
            ask_sz = int(max(20, 220 / (level + 1) + random.uniform(-25, 25)))
            bids.append({"price": bid_px, "size": bid_sz})
            asks.append({"price": ask_px, "size": ask_sz})
            total_depth += bid_sz + ask_sz

        bid_sum = sum(level["size"] for level in bids)
        ask_sum = sum(level["size"] for level in asks)
        imbalance = (bid_sum - ask_sum) / max(1, bid_sum + ask_sum)
        signed_flow = (bid_sum - ask_sum) / max(1, total_depth)

        recent_orders = [
                {
                    "ts": float(self._step),
                    "order_id": f"MO-O-{self._step}-{i}",
                    "agent_id": "MOCK_FEED",
                    "side": "BUY" if i % 2 == 0 else "SELL",
                    "order_type": "LIMIT",
                    "price": bids[0]["price"] if i % 2 == 0 else asks[0]["price"],
                    "quantity": int(20 + random.random() * 100),
                    "status": "Submitted",
                }
                for i in range(4)
            ]
        recent_trades = [
                {
                    "ts": float(self._step),
                    "trade_id": f"MO-T-{self._step}-{i}",
                    "price": round(mid + (random.random() - 0.5) * 0.03, 3),
                    "quantity": int(10 + random.random() * 80),
                    "buyer_agent_id": "MOCK_BUYER",
                    "seller_agent_id": "MOCK_SELLER",
                    "aggressor_side": "BUY" if random.random() > 0.5 else "SELL",
                }
                for i in range(3)
            ]
        recent_events = [
                {
                    "ts": float(self._step),
                    "type": "Kernel",
                    "severity": "warning",
                    "message": "Using fallback mock live feed",
                    "metadata": {},
                }
            ]

        state = build_market_state(
            step=self._step,
            current_time=float(self._step),
            duration_seconds=self.duration_seconds,
            bids=bids,
            asks=asks,
            price_history=[base_mid, mid],
            signed_flow_history=deque([signed_flow], maxlen=5),
            recent_trades=recent_trades,
            recent_events=recent_events,
            recent_orders=recent_orders,
        )

        if state is None:
            raise RuntimeError("MockLiveFeedAdapter failed to build normalized state")

        self._last_state = state
        self._last_update_ts = state.current_time
        self._last_update_wall_time = time.time()
        return state

    def latest_state(self) -> Optional[MarketState]:
        if not self._running:
            return None
        return self._build_next()

    def health(self) -> FeedHealth:
        return FeedHealth(
            connected=True,
            source="mock",
            provider="mock",
            last_update_ts=self._last_update_ts,
            last_update_wall_time=self._last_update_wall_time,
            fallback_active=False,
            stale=False,
            latency_ms=0.0,
            transport="synthetic",
            message="Mock live-feed provider",
        )
