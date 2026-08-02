"""Build leakage-safe liquidity-shock samples from LOBSTER snapshots."""

from __future__ import annotations

from pathlib import Path

import numpy as np


FEATURE_NAMES = (
    "spread_bps",
    "depth_log",
    "imbalance",
    "spread_ratio",
    "depth_ratio",
    "depth_change_ratio",
)


def select_probability_threshold(probabilities: np.ndarray, labels: np.ndarray) -> float:
    best_threshold = 0.5
    best_f1 = -1.0
    for threshold in np.linspace(0.05, 0.95, 91):
        predicted = probabilities >= threshold
        true_positive = float(np.sum(predicted & (labels == 1)))
        false_positive = float(np.sum(predicted & (labels == 0)))
        false_negative = float(np.sum(~predicted & (labels == 1)))
        precision = true_positive / max(1.0, true_positive + false_positive)
        recall = true_positive / max(1.0, true_positive + false_negative)
        f1 = 2 * precision * recall / max(1e-12, precision + recall)
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = float(threshold)
    return best_threshold


def load_lobster_orderbook(path: Path) -> np.ndarray:
    rows = np.loadtxt(Path(path), delimiter=",", dtype=np.float64)
    if rows.ndim != 2 or rows.shape[1] < 4 or rows.shape[1] % 4:
        raise ValueError("LOBSTER orderbook must contain four columns per level.")
    return rows


def _market_values(rows: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    asks = rows[:, 0::4]
    ask_sizes = rows[:, 1::4]
    bids = rows[:, 2::4]
    bid_sizes = rows[:, 3::4]
    mid = (asks[:, 0] + bids[:, 0]) / 2.0
    spread_bps = (asks[:, 0] - bids[:, 0]) / mid * 10_000
    depth = ask_sizes.sum(axis=1) + bid_sizes.sum(axis=1)
    imbalance = (bid_sizes.sum(axis=1) - ask_sizes.sum(axis=1)) / np.maximum(depth, 1.0)
    return spread_bps, depth, imbalance


def build_liquidity_samples(
    orderbook: np.ndarray,
    *,
    baseline_events: int = 100,
    horizon_events: int = 20,
    sample_step: int = 10,
    spread_multiplier: float = 2.5,
    depth_ratio_threshold: float = 0.4,
) -> list[dict[str, object]]:
    """Create features from past snapshots and labels from a future window."""
    if baseline_events < 1 or horizon_events < 1 or sample_step < 1:
        raise ValueError("Baseline, horizon, and sample step must be positive.")
    spread, depth, imbalance = _market_values(np.asarray(orderbook, dtype=np.float64))
    samples: list[dict[str, object]] = []
    last_index = len(spread) - horizon_events
    for index in range(baseline_events, last_index, sample_step):
        baseline_spread = float(np.median(spread[index - baseline_events:index]))
        baseline_depth = float(np.median(depth[index - baseline_events:index]))
        if baseline_spread <= 0 or baseline_depth <= 0:
            continue
        current_depth = float(depth[index])
        future_spread = spread[index + 1:index + horizon_events + 1]
        future_depth = depth[index + 1:index + horizon_events + 1]
        samples.append({
            "features": {
                "spread_bps": float(spread[index]),
                "depth_log": float(np.log1p(current_depth)),
                "imbalance": float(imbalance[index]),
                "spread_ratio": float(spread[index] / baseline_spread),
                "depth_ratio": float(current_depth / baseline_depth),
                "depth_change_ratio": float(current_depth / max(depth[index - 1], 1e-12)),
            },
            "label": int(
                np.any(future_spread >= baseline_spread * spread_multiplier)
                or np.any(future_depth <= baseline_depth * depth_ratio_threshold)
            ),
            "index": index,
        })
    return samples
