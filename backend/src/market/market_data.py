"""Shared OHLCV data shape and replay helpers."""

from __future__ import annotations
from dataclasses import dataclass
from typing import List
import math
import numpy as np


@dataclass
class StockInfo:
    ticker: str
    name: str
    currency: str
    last_close: float
    period_start: str
    period_end: str
    bars: int
    prices: List[float]
    volumes: List[float]
    highs: List[float]
    lows: List[float]
    returns: List[float]
    realized_vol: float
    mean_return: float


def bar_return_price_sigma(info: StockInfo, reference_price: float) -> float:
    """Convert per-bar log-return volatility into absolute price noise."""
    price = max(0.01, float(reference_price))
    returns = []
    for value in info.returns:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed):
            returns.append(parsed)

    if returns:
        return max(0.001, float(np.std(returns)) * price)

    try:
        annualized_vol = float(info.realized_vol)
    except (TypeError, ValueError):
        annualized_vol = 0.0
    if math.isfinite(annualized_vol) and annualized_vol > 0:
        return max(0.001, annualized_vol / float(np.sqrt(252)) * price)
    return 0.001


def build_oracle_path(info: StockInfo, target_steps: int = 500) -> List[float]:
    """Resample/extend real prices to target_steps for the oracle."""
    prices = info.prices[:]
    if len(prices) >= target_steps:
        indices = [int(i * (len(prices) - 1) / (target_steps - 1)) for i in range(target_steps)]
        return [prices[i] for i in indices]

    rng = np.random.RandomState(42)
    kappa, r_bar = 0.05, info.last_close
    sigma = bar_return_price_sigma(info, r_bar)
    extended = list(prices)
    while len(extended) < target_steps:
        prev = extended[-1]
        nxt = max(0.01, prev + kappa * (r_bar - prev) + sigma * rng.randn())
        extended.append(float(nxt))
    return extended[:target_steps]
