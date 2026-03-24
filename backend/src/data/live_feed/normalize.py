"""Unified normalization helpers for provider-specific market feeds."""

from __future__ import annotations

import math
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from .base import MarketState


def compute_volatility(price_history: List[float]) -> float:
    if len(price_history) < 10:
        return 0.0

    returns = []
    for i in range(1, len(price_history)):
        prev = price_history[i - 1]
        curr = price_history[i]
        if prev > 0 and curr > 0:
            returns.append(math.log(curr / prev))

    if len(returns) < 2:
        return 0.0

    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(max(var, 0.0)) * math.sqrt(252 * 390)


def build_market_state(
    *,
    step: int,
    current_time: float,
    duration_seconds: int,
    bids: List[Dict[str, float]],
    asks: List[Dict[str, float]],
    price_history: List[float],
    signed_flow_history: Deque[float],
    recent_trades: List[Dict[str, Any]],
    recent_events: List[Dict[str, Any]],
    recent_orders: Optional[List[Dict[str, Any]]] = None,
) -> Optional[MarketState]:
    if not bids or not asks:
        return None

    best_bid = float(bids[0]["price"])
    best_ask = float(asks[0]["price"])
    if best_bid <= 0 or best_ask <= 0:
        return None

    mid = (best_bid + best_ask) / 2
    spread = max(0.0, best_ask - best_bid)

    bid_sum = sum(float(level["size"]) for level in bids[:10])
    ask_sum = sum(float(level["size"]) for level in asks[:10])
    total_depth = int(bid_sum + ask_sum)
    imbalance = (bid_sum - ask_sum) / max(1.0, bid_sum + ask_sum)

    prices = list(price_history)
    if len(prices) >= 6 and prices[-6] != 0:
        recent_price_change = (prices[-1] - prices[-6]) / prices[-6]
    else:
        recent_price_change = 0.0

    signed_flow = sum(signed_flow_history)
    trade_flow = signed_flow / max(1.0, bid_sum + ask_sum)

    return MarketState(
        current_time=current_time,
        current_price=mid,
        mid_price=mid,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        total_depth=total_depth,
        order_book_imbalance=imbalance,
        trade_flow=trade_flow,
        recent_price_change=recent_price_change,
        recent_signed_volume=signed_flow,
        time_to_close=max(0.0, duration_seconds - current_time),
        volatility=compute_volatility(prices),
        step=step,
        order_book_levels={"bids": bids[:10], "asks": asks[:10]},
        recent_orders=recent_orders or [],
        recent_trades=recent_trades[-20:],
        recent_events=recent_events[-20:],
    )
