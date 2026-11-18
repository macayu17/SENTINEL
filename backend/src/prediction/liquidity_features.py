"""Online liquidity features, shared by LOBSTER training and the live predictor.

Both sides feed one observation per second into the same tracker, so the model
sees identical feature definitions in training and at runtime. Every feature is
scale-free (ratios against the instrument's own recent baseline), because a
$580 AAPL book and a $100 simulated book only compare in relative terms.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import islice
from statistics import median
import math

FEATURE_NAMES = (
    "spread_ratio",       # spread vs gated 60 s median
    "depth_ratio",        # visible depth vs gated 60 s median
    "bid_depth_ratio",
    "ask_depth_ratio",
    "depth_change_1s",    # depth now / 1 s ago
    "depth_change_5s",    # depth now / 5 s ago
    "spread_change_5s",   # spread now / 5 s ago
    "imbalance",          # 10-level (bid - ask) / (bid + ask)
    "top_imbalance",      # level-1 queue imbalance
    "vol_ratio",          # 10 s realized vol vs its 60 s median
    "flow_pressure",      # signed aggressor volume, last 10 s, / visible depth
    "recent_stress",      # share of the last 60 s spent in a shock state
    "max_spread_ratio_10s",
    "min_depth_ratio_10s",
    "since_stress",       # seconds since the last shock state, / 300, capped at 1
    # Longer memory: is the 60 s baseline itself unusually tight or deep?
    "depth_change_30s",
    "max_spread_ratio_60s",
    "min_depth_ratio_60s",
    "stress_300s",
    "stress_900s",
    "spread_ratio_300s",  # spread vs its 5 min median
    "spread_ratio_900s",
    "depth_ratio_300s",
    "depth_ratio_900s",
    "baseline_vs_300s",   # the 60 s spread baseline vs the 5 min median spread
    "vol_ratio_300s",     # 10 s return std vs the 5 min one
    # Book shape (10 levels)
    "near_share",         # share of visible depth in the top 3 levels per side
    "span_ratio",         # price span of the 10 levels vs its 60 s median
    "depth_dist_ratio",   # size-weighted distance of depth from mid vs its 60 s median
    # Variability and activity
    "depth_volatility_10s",
    "spread_vol_10s",
    "abs_flow_30s",       # mean |signed aggressor volume| over 30 s / visible depth
)
STRESS_MEMORY_SECONDS = 300

BASELINE_SECONDS = 60
# A stressed observation is kept out of the baseline, so a shock cannot become "normal".
BASELINE_SPREAD_CEILING = 2.5
BASELINE_DEPTH_FLOOR = 0.4


@dataclass(frozen=True)
class BookObservation:
    mid: float
    spread: float
    bid_depth: float
    ask_depth: float
    top_bid_size: float
    top_ask_size: float
    signed_volume_10s: float
    # Up to 10 (price, size) levels per side, best first; empty when unknown.
    bid_levels: tuple[tuple[float, float], ...] = ()
    ask_levels: tuple[tuple[float, float], ...] = ()


def _ratio(a: float, b: float) -> float:
    return a / b if b > 0 else 1.0


def _std(values) -> float:
    """Sample standard deviation; 0 below two points."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


def _past_ratio(value: float, past: deque) -> float:
    """value / median of the past window (excludes now); 1 with no usable past."""
    return _ratio(value, median(past)) if past else 1.0


def _book_shape(obs: BookObservation, mid: float, depth: float) -> tuple[float, float, float]:
    """(near_share, span_bps, size-weighted distance from mid in bps)."""
    bids = [lv for lv in obs.bid_levels if lv[1] > 0]
    asks = [lv for lv in obs.ask_levels if lv[1] > 0]
    if not bids or not asks:
        return 1.0, 0.0, 0.0
    near = sum(size for _, size in bids[:3]) + sum(size for _, size in asks[:3])
    span = (max(p for p, _ in asks) - min(p for p, _ in bids)) / mid * 10_000
    weighted = sum(size * (mid - p) for p, size in bids) + sum(size * (p - mid) for p, size in asks)
    return near / depth, span, weighted / depth / mid * 10_000


class LiquidityFeatureTracker:
    """Feed one observation per second; returns the feature dict and the baseline used."""

    def __init__(self, baseline_seconds: int = BASELINE_SECONDS) -> None:
        self._baseline: deque[tuple[float, float, float, float]] = deque(maxlen=baseline_seconds)
        self._history: deque[tuple[float, float, float]] = deque(maxlen=6)  # (spread_bps, depth, mid)
        self._returns: deque[float] = deque(maxlen=10)
        self._vols: deque[float] = deque(maxlen=baseline_seconds)
        self._stressed: deque[bool] = deque(maxlen=baseline_seconds)
        self._recent: deque[tuple[float, float]] = deque(maxlen=10)  # (spread_ratio, depth_ratio)
        self._since_stress = STRESS_MEMORY_SECONDS
        self._depths: deque[float] = deque(maxlen=31)          # depth, last 31 s (30 s change)
        self._recent60: deque[tuple[float, float]] = deque(maxlen=60)
        self._stress900: deque[bool] = deque(maxlen=900)
        self._spreads300: deque[float] = deque(maxlen=300)     # past spread_bps
        self._spreads900: deque[float] = deque(maxlen=900)
        self._depths300: deque[float] = deque(maxlen=300)
        self._depths900: deque[float] = deque(maxlen=900)
        self._returns300: deque[float] = deque(maxlen=300)     # past log returns
        self._spans: deque[float] = deque(maxlen=baseline_seconds)
        self._dists: deque[float] = deque(maxlen=baseline_seconds)
        self._log_depth_diffs: deque[float] = deque(maxlen=10)
        self._spread_ratios: deque[float] = deque(maxlen=10)
        self._abs_flows: deque[float] = deque(maxlen=30)

    def update(self, obs: BookObservation) -> tuple[dict[str, float], tuple[float, float]]:
        mid = max(obs.mid, 1e-9)
        spread_bps = max(0.0, obs.spread) / mid * 10_000
        bid, ask = max(0.0, obs.bid_depth), max(0.0, obs.ask_depth)
        depth = max(1.0, bid + ask)

        current = (spread_bps, depth, max(1.0, bid), max(1.0, ask))
        base = self._baseline or [current]
        base_spread = median(b[0] for b in base)
        base_depth = median(b[1] for b in base)
        base_bid = median(b[2] for b in base)
        base_ask = median(b[3] for b in base)

        previous = self._history[-1] if self._history else (spread_bps, depth, mid)
        five_ago = self._history[0] if len(self._history) == 6 else previous
        ret = math.log(mid / previous[2]) if self._history and previous[2] > 0 else None
        if ret is not None:
            self._returns.append(ret)
        rv = math.sqrt(sum(r * r for r in self._returns) / len(self._returns)) if self._returns else 0.0
        base_rv = median(self._vols) if self._vols else rv

        top = obs.top_bid_size + obs.top_ask_size
        spread_floor = 1e-6
        features = {
            "spread_ratio": _ratio(spread_bps, max(base_spread, spread_floor)),
            "depth_ratio": _ratio(depth, base_depth),
            "bid_depth_ratio": _ratio(max(1.0, bid), base_bid),
            "ask_depth_ratio": _ratio(max(1.0, ask), base_ask),
            "depth_change_1s": _ratio(depth, previous[1]),
            "depth_change_5s": _ratio(depth, five_ago[1]),
            "spread_change_5s": _ratio(spread_bps, max(five_ago[0], spread_floor)),
            "imbalance": (bid - ask) / depth,
            "top_imbalance": (obs.top_bid_size - obs.top_ask_size) / top if top > 0 else 0.0,
            "vol_ratio": _ratio(rv, base_rv) if base_rv > 0 else (1.0 if rv == 0 else 2.0),
            "flow_pressure": obs.signed_volume_10s / depth,
        }

        calm = features["spread_ratio"] <= BASELINE_SPREAD_CEILING and features["depth_ratio"] >= BASELINE_DEPTH_FLOOR
        self._stressed.append(not calm)
        self._recent.append((features["spread_ratio"], features["depth_ratio"]))
        self._since_stress = 0 if not calm else min(STRESS_MEMORY_SECONDS, self._since_stress + 1)
        features["recent_stress"] = sum(self._stressed) / len(self._stressed)
        features["max_spread_ratio_10s"] = max(r[0] for r in self._recent)
        features["min_depth_ratio_10s"] = min(r[1] for r in self._recent)
        features["since_stress"] = self._since_stress / STRESS_MEMORY_SECONDS

        # Longer memory.
        self._depths.append(depth)
        self._recent60.append((features["spread_ratio"], features["depth_ratio"]))
        self._stress900.append(not calm)
        features["depth_change_30s"] = _ratio(depth, self._depths[0])
        features["max_spread_ratio_60s"] = max(r[0] for r in self._recent60)
        features["min_depth_ratio_60s"] = min(r[1] for r in self._recent60)
        last300 = list(islice(reversed(self._stress900), 300))
        features["stress_300s"] = sum(last300) / len(last300)
        features["stress_900s"] = sum(self._stress900) / len(self._stress900)
        long_spread = median(self._spreads300) if self._spreads300 else spread_bps
        features["spread_ratio_300s"] = _past_ratio(spread_bps, self._spreads300)
        features["spread_ratio_900s"] = _past_ratio(spread_bps, self._spreads900)
        features["depth_ratio_300s"] = _past_ratio(depth, self._depths300)
        features["depth_ratio_900s"] = _past_ratio(depth, self._depths900)
        features["baseline_vs_300s"] = base_spread / max(long_spread, spread_floor)
        long_vol = _std(self._returns300) if len(self._returns300) >= 10 else 0.0
        short_vol = _std(self._returns)
        features["vol_ratio_300s"] = short_vol / long_vol if long_vol > 0 else 1.0

        # Book shape.
        near_share, span, dist = _book_shape(obs, mid, depth)
        features["near_share"] = near_share
        features["span_ratio"] = _past_ratio(span, self._spans) if span > 0 else 1.0
        features["depth_dist_ratio"] = _past_ratio(dist, self._dists) if dist > 0 else 1.0

        # Variability and activity.
        if self._history:
            self._log_depth_diffs.append(math.log(depth / previous[1]))
        self._spread_ratios.append(features["spread_ratio"])
        self._abs_flows.append(abs(obs.signed_volume_10s))
        features["depth_volatility_10s"] = _std(self._log_depth_diffs)
        features["spread_vol_10s"] = _std(self._spread_ratios)
        features["abs_flow_30s"] = sum(self._abs_flows) / len(self._abs_flows) / depth

        if calm:
            self._baseline.append(current)
        self._history.append((spread_bps, depth, mid))
        self._vols.append(rv)
        self._spreads300.append(spread_bps)
        self._spreads900.append(spread_bps)
        self._depths300.append(depth)
        self._depths900.append(depth)
        if ret is not None:
            self._returns300.append(ret)
        if span > 0:
            self._spans.append(span)
        if dist > 0:
            self._dists.append(dist)
        return features, (base_spread, base_depth)


def observation_from_state(state: dict) -> BookObservation:
    """Simulator market_state -> observation. Mirrors what LOBSTER snapshots provide."""
    bids = state.get("bid_levels") or []
    asks = state.get("ask_levels") or []
    return BookObservation(
        mid=float(state.get("mid_price") or state.get("current_price") or 0.0),
        spread=float(state.get("spread") or 0.0),
        bid_depth=float(state.get("bid_depth") or 0.0),
        ask_depth=float(state.get("ask_depth") or 0.0),
        top_bid_size=float(bids[0]["size"]) if bids else 0.0,
        top_ask_size=float(asks[0]["size"]) if asks else 0.0,
        signed_volume_10s=float(state.get("recent_signed_volume") or 0.0),
        bid_levels=tuple((float(lv["price"]), float(lv["size"])) for lv in bids[:10]),
        ask_levels=tuple((float(lv["price"]), float(lv["size"])) for lv in asks[:10]),
    )
