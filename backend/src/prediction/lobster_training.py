"""Leakage-safe liquidity-shock samples from LOBSTER order book + message files.

Each trading day is resampled to a 1-second grid and fed through the same
LiquidityFeatureTracker the live predictor uses. The label looks strictly
forward: within the next `horizon` seconds, does the spread reach
`spread_multiplier`x its baseline, or visible depth fall to `depth_floor` of it?
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .liquidity_features import FEATURE_NAMES, BookObservation, LiquidityFeatureTracker

OPEN_SECONDS, CLOSE_SECONDS = 34_200, 57_600   # 09:30 and 16:00, seconds after midnight
PRICE_SCALE = 10_000                              # LOBSTER prices are dollars x 10,000
FLOW_WINDOW = 10
EXECUTION_TYPES = (4, 5)                          # visible and hidden executions


def select_probability_threshold(probabilities: np.ndarray, labels: np.ndarray) -> float:
    """The probability cut that maximises F1 on a validation set."""
    best_threshold, best_f1 = 0.5, -1.0
    for threshold in np.linspace(0.05, 0.95, 91):
        predicted = probabilities >= threshold
        tp = float(np.sum(predicted & (labels == 1)))
        fp = float(np.sum(predicted & (labels == 0)))
        fn = float(np.sum(~predicted & (labels == 1)))
        precision = tp / max(1.0, tp + fp)
        recall = tp / max(1.0, tp + fn)
        f1 = 2 * precision * recall / max(1e-12, precision + recall)
        if f1 > best_f1:
            best_f1, best_threshold = f1, float(threshold)
    return best_threshold


def load_day(orderbook_path: Path, message_path: Path) -> tuple[np.ndarray, np.ndarray]:
    orderbook = np.loadtxt(orderbook_path, delimiter=",", dtype=np.float64)
    messages = np.loadtxt(message_path, delimiter=",", dtype=np.float64, usecols=(0, 1, 3, 5))
    if orderbook.ndim != 2 or orderbook.shape[1] % 4 or len(orderbook) != len(messages):
        raise ValueError("Expected aligned LOBSTER orderbook (4 columns per level) and message files.")
    return orderbook, messages


def grid_observations(orderbook: np.ndarray, messages: np.ndarray) -> list[BookObservation]:
    """The book as it stood at the end of every second of the session."""
    times = messages[:, 0]
    executed = np.isin(messages[:, 1], EXECUTION_TYPES)
    # Direction is the resting order's side; the aggressor is the other one.
    signed = np.where(executed, -messages[:, 3] * messages[:, 2], 0.0)
    cumulative = np.concatenate([[0.0], np.cumsum(signed)])

    grid = np.arange(OPEN_SECONDS + 1, CLOSE_SECONDS + 1, 1.0)
    row = np.searchsorted(times, grid, side="right") - 1
    valid = row >= 0
    grid, row = grid[valid], row[valid]
    window_row = np.searchsorted(times, grid - FLOW_WINDOW, side="right") - 1
    flow = cumulative[row + 1] - cumulative[window_row + 1]

    book = orderbook[row]
    ask_px, ask_sz = book[:, 0::4] / PRICE_SCALE, book[:, 1::4]
    bid_px, bid_sz = book[:, 2::4] / PRICE_SCALE, book[:, 3::4]
    out = []
    for i in range(len(book)):
        bids = tuple((p, z) for p, z in zip(bid_px[i].tolist(), bid_sz[i].tolist()) if z > 0)
        asks = tuple((p, z) for p, z in zip(ask_px[i].tolist(), ask_sz[i].tolist()) if z > 0)
        out.append(BookObservation(
            mid=(ask_px[i, 0] + bid_px[i, 0]) / 2, spread=ask_px[i, 0] - bid_px[i, 0],
            bid_depth=float(bid_sz[i].sum()), ask_depth=float(ask_sz[i].sum()),
            top_bid_size=float(bid_sz[i, 0]), top_ask_size=float(ask_sz[i, 0]),
            signed_volume_10s=float(flow[i]), bid_levels=bids, ask_levels=asks,
        ))
    return out


def build_samples(
    observations: list[BookObservation],
    *,
    horizon: int = 60,
    spread_multiplier: float = 2.5,
    depth_floor: float = 0.4,
    warmup: int = 60,
) -> tuple[np.ndarray, np.ndarray]:
    """Features from the past, labels from the next `horizon` observations. Returns (X, y)."""
    tracker = LiquidityFeatureTracker()
    rows, base_spread, base_depth = [], [], []
    for obs in observations:
        features, (spread_ref, depth_ref) = tracker.update(obs)
        rows.append([features[name] for name in FEATURE_NAMES])
        base_spread.append(spread_ref)
        base_depth.append(depth_ref)

    spread_bps = np.array([max(0.0, o.spread) / max(o.mid, 1e-9) * 10_000 for o in observations])
    depth = np.array([max(1.0, o.bid_depth + o.ask_depth) for o in observations])
    n = len(observations) - horizon
    if n <= warmup:
        return np.empty((0, len(FEATURE_NAMES))), np.empty(0, dtype=np.int8)
    future_spread = sliding_window_view(spread_bps[1:], horizon).max(axis=1)[:n]
    future_depth = sliding_window_view(depth[1:], horizon).min(axis=1)[:n]
    labels = (
        (future_spread >= spread_multiplier * np.asarray(base_spread[:n]))
        | (future_depth <= depth_floor * np.asarray(base_depth[:n]))
    ).astype(np.int8)
    X = np.asarray(rows[:n], dtype=np.float64)
    return X[warmup:], labels[warmup:]
