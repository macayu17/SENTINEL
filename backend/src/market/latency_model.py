"""Latency model ported from ABIDES — simulates realistic network delays.

Three modes:
  ZERO            — instant delivery (debugging)
  DETERMINISTIC   — fixed delay per agent tier
  CUBIC           — jitter sampled from 1/x³ (heavy tailed, models congestion)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

import numpy as np


class LatencyMode(Enum):
    ZERO = auto()
    DETERMINISTIC = auto()
    CUBIC = auto()


# Tier → one-way base delay in seconds
_TIER_DELAYS = {
    "HFT":           0.000_001,   #  1 μs — co-located
    "MarketMaker":   0.000_050,   # 50 μs — exchange member
    "Institutional": 0.001_000,   #  1 ms — direct market access
    "Informed":      0.002_000,   #  2 ms
    "Momentum":      0.002_500,
    "MeanReversion": 0.002_500,
    "Spoofing":      0.000_800,
    "Sentiment":     0.005_000,
    "Retail":        0.010_000,   # 10 ms — consumer ISP
    "Noise":         0.015_000,   # 15 ms
    "RL_MM":         0.000_050,   # same as market maker
    "LiquidityTrader": 0.003_000,
}


@dataclass
class LatencyConfig:
    mode: LatencyMode = LatencyMode.DETERMINISTIC
    jitter_exponent: float = 3.0        # cubic tail for CUBIC mode
    min_jitter_ns: float = 100.0        # floor in nanoseconds
    max_jitter_ns: float = 50_000_000.0 # 50 ms ceiling


class LatencyModel:
    """Compute one-way communication delay between an agent and the exchange."""

    def __init__(
        self,
        config: Optional[LatencyConfig] = None,
        rng: Optional[np.random.RandomState] = None,
    ) -> None:
        self.config = config or LatencyConfig()
        self.rng = rng or np.random.RandomState()

    def get_latency(self, agent_type: str) -> float:
        """Return one-way latency in seconds for the given agent type."""
        mode = self.config.mode

        if mode == LatencyMode.ZERO:
            return 0.0

        base = _TIER_DELAYS.get(agent_type, 0.010)

        if mode == LatencyMode.DETERMINISTIC:
            return base

        # CUBIC mode — base + heavy-tailed jitter
        u = self.rng.uniform(0.01, 1.0)
        jitter_ns = self.config.min_jitter_ns / (u ** (1.0 / self.config.jitter_exponent))
        jitter_ns = min(jitter_ns, self.config.max_jitter_ns)
        jitter_sec = jitter_ns * 1e-9
        return base + jitter_sec

    def describe(self) -> dict:
        return {
            "mode": self.config.mode.name,
            "jitter_exponent": self.config.jitter_exponent,
            "tiers": {k: f"{v*1e6:.0f}μs" for k, v in _TIER_DELAYS.items()},
        }
