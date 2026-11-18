"""Mean-reverting fundamental value oracle.

Generates a hidden "true" price with an Ornstein-Uhlenbeck process plus rare
news jumps. Informed agents may observe the current value; the market at large
only learns it `public_lag_seconds` later, which is what gives private
information its edge.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np


@dataclass
class OracleConfig:
    """Parameters for the mean-reverting oracle."""

    r_bar: float = 100.0
    kappa: float = 0.05
    sigma_s: float = 0.02
    observation_noise: float = 0.005
    enabled: bool = True
    jump_rate: float = 1 / 1800          # news events per second (~13 per session)
    jump_sigma_pct: float = 0.0015       # jump size, as a fraction of the value
    public_lag_seconds: int = 30         # how stale the publicly known value is


class MeanRevertingOracle:
    """Ornstein-Uhlenbeck fundamental value process with Poisson news jumps."""

    def __init__(self, config: Optional[OracleConfig] = None) -> None:
        self.config = config or OracleConfig()
        self.rng = np.random.RandomState()
        self.reset()

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @property
    def public_value(self) -> float:
        """The value as the public knows it: `public_lag_seconds` behind."""
        return self._history[0]

    def reset(self, seed: Optional[int] = None) -> None:
        if seed is not None:
            self.rng = np.random.RandomState(seed)
        self.current_value = self.config.r_bar
        self._history = deque([self.current_value], maxlen=max(0, self.config.public_lag_seconds) + 1)

    def advance(self, dt: float = 1.0) -> float:
        """Advance the process by dt seconds and return the new fundamental value."""
        if self.config.enabled:
            drift = self.config.kappa * (self.config.r_bar - self.current_value) * dt
            diffusion = self.config.sigma_s * np.sqrt(dt) * self.rng.randn()
            if self.rng.rand() < self.config.jump_rate * dt:
                diffusion += self.config.jump_sigma_pct * self.current_value * self.rng.randn()
            self.current_value = max(0.01, self.current_value + drift + diffusion)
            self._history.append(self.current_value)
        return self.current_value

    def get_mispricing(self, market_price: float) -> Dict:
        diff = market_price - self.current_value
        return {
            "fundamental_value": self.current_value,
            "mispricing": diff,
            "mispricing_pct": diff / self.current_value * 100,
            "observation_noise": self.config.observation_noise,
        }
