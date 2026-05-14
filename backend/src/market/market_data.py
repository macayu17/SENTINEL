"""Real-world market data fetcher for SENTINEL sandbox replay.

Fetches OHLCV history via yfinance and converts it into a form the
simulator can consume as an oracle replay path.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List
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


def fetch_stock(ticker: str, period: str = "1mo", interval: str = "1d") -> StockInfo:
    """Download OHLCV data from Yahoo Finance."""
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance is not installed. Run: pip install yfinance")

    tkr = yf.Ticker(ticker)
    hist = tkr.history(period=period, interval=interval, auto_adjust=True)

    if hist.empty:
        raise ValueError(f"No data returned for ticker '{ticker}'.")

    closes = hist["Close"].dropna().tolist()
    volumes = hist["Volume"].dropna().tolist()
    highs = hist["High"].dropna().tolist()
    lows = hist["Low"].dropna().tolist()

    n = min(len(closes), len(volumes), len(highs), len(lows))
    closes, volumes, highs, lows = closes[:n], volumes[:n], highs[:n], lows[:n]

    if n < 2:
        raise ValueError(f"Not enough data for '{ticker}' ({n} bars).")

    log_returns = [
        float(np.log(closes[i] / closes[i - 1]))
        for i in range(1, n)
        if closes[i] > 0 and closes[i - 1] > 0
    ]

    bars_per_year = {"1m": 252*390, "5m": 252*78, "15m": 252*26, "1h": 252*6.5, "1d": 252, "1wk": 52}.get(interval, 252)
    std = float(np.std(log_returns)) if log_returns else 0.01
    realized_vol = std * float(np.sqrt(bars_per_year))
    mean_return = float(np.mean(log_returns)) if log_returns else 0.0

    try:
        info = tkr.fast_info
        name = getattr(info, "long_name", None) or ticker
        currency = getattr(info, "currency", "USD") or "USD"
    except Exception:
        name, currency = ticker, "USD"

    index = hist.index
    return StockInfo(
        ticker=ticker.upper(), name=str(name), currency=str(currency),
        last_close=float(closes[-1]),
        period_start=str(index[0].date()) if hasattr(index[0], "date") else str(index[0])[:10],
        period_end=str(index[-1].date()) if hasattr(index[-1], "date") else str(index[-1])[:10],
        bars=n, prices=closes, volumes=volumes, highs=highs, lows=lows,
        returns=log_returns, realized_vol=round(realized_vol, 4), mean_return=round(mean_return, 6),
    )


def build_oracle_path(info: StockInfo, target_steps: int = 500) -> List[float]:
    """Resample/extend real prices to target_steps for the oracle."""
    prices = info.prices[:]
    if len(prices) >= target_steps:
        indices = [int(i * (len(prices) - 1) / (target_steps - 1)) for i in range(target_steps)]
        return [prices[i] for i in indices]

    rng = np.random.RandomState(42)
    sigma = info.realized_vol / np.sqrt(252)
    kappa, r_bar = 0.05, info.last_close
    extended = list(prices)
    while len(extended) < target_steps:
        prev = extended[-1]
        nxt = max(0.01, prev + kappa * (r_bar - prev) + sigma * rng.randn())
        extended.append(float(nxt))
    return extended[:target_steps]


POPULAR_TICKERS = [
    {"ticker": "AAPL", "name": "Apple Inc."},
    {"ticker": "TSLA", "name": "Tesla Inc."},
    {"ticker": "MSFT", "name": "Microsoft Corp."},
    {"ticker": "GOOGL", "name": "Alphabet Inc."},
    {"ticker": "AMZN", "name": "Amazon.com Inc."},
    {"ticker": "NVDA", "name": "NVIDIA Corp."},
    {"ticker": "META", "name": "Meta Platforms"},
    {"ticker": "NFLX", "name": "Netflix Inc."},
    {"ticker": "SPY", "name": "S&P 500 ETF"},
    {"ticker": "BTC-USD", "name": "Bitcoin / USD"},
    {"ticker": "^NSEI", "name": "NIFTY 50 (India)"},
    {"ticker": "^BSESN", "name": "SENSEX (India)"},
]
