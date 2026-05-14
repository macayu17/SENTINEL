"""Mean-Reverting Fundamental Value Oracle (ABIDES-inspired).

Generates a "true" hidden price via an Ornstein-Uhlenbeck process.
Informed agents can observe a noisy version; the gap between market
price and fundamental drives trading opportunities.

Supports two modes:
  - Synthetic: OU random walk anchored to r_bar
  - Replay:    Steps through a real historical price series
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


@dataclass
class OracleConfig:
    """Parameters for the mean-reverting oracle."""

    r_bar: float = 100.0
    kappa: float = 0.05
    sigma_s: float = 0.02
    observation_noise: float = 0.005
    enabled: bool = True
    replay_path: List[float] = field(default_factory=list)


class MeanRevertingOracle:
    """Ornstein-Uhlenbeck fundamental value process.

    Usage:
        oracle = MeanRevertingOracle(OracleConfig(r_bar=100, kappa=0.05))
        for _ in range(1000):
            true_val  = oracle.advance(dt=1.0)
            noisy_obs = oracle.observe()
    """

    def __init__(self, config: Optional[OracleConfig] = None, rng: Optional[np.random.RandomState] = None) -> None:
        self.config = config or OracleConfig()
        self.rng = rng or np.random.RandomState()
        self._current_value: float = self.config.r_bar
        self._history: List[float] = [self._current_value]
        self._time: float = 0.0
        self._replay_index: int = 0

    @property
    def current_value(self) -> float:
        return self._current_value

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def reset(self, seed: Optional[int] = None) -> None:
        if seed is not None:
            self.rng = np.random.RandomState(seed)
        self._current_value = self.config.r_bar
        self._history = [self._current_value]
        self._time = 0.0
        self._replay_index = 0

    def advance(self, dt: float = 1.0) -> float:
        """Advance oracle by dt seconds. Returns new fundamental value."""
        if not self.config.enabled:
            return self._current_value

        # Replay mode
        if self.config.replay_path:
            path = self.config.replay_path
            if self._replay_index < len(path):
                self._current_value = float(path[self._replay_index])
                self._replay_index += 1
            else:
                sigma = self.config.sigma_s
                noise = sigma * np.sqrt(dt) * self.rng.randn()
                self._current_value = max(0.01, self._current_value + noise)
            self._history.append(self._current_value)
            self._time += dt
            return self._current_value

        # Synthetic OU mode
        kappa = self.config.kappa
        r_bar = self.config.r_bar
        sigma = self.config.sigma_s
        drift = kappa * (r_bar - self._current_value) * dt
        diffusion = sigma * np.sqrt(dt) * self.rng.randn()
        self._current_value += drift + diffusion
        self._current_value = max(self._current_value, 0.01)
        self._history.append(self._current_value)
        self._time += dt
        return self._current_value

    def observe(self, sigma_n: Optional[float] = None) -> float:
        """Return a noisy observation of the fundamental value."""
        if not self.config.enabled:
            return self._current_value
        noise_std = sigma_n if sigma_n is not None else self.config.observation_noise
        return self._current_value + noise_std * self.rng.randn()

    def get_mispricing(self, market_price: float) -> Dict:
        diff = market_price - self._current_value
        pct = (diff / self._current_value * 100) if self._current_value > 0 else 0.0
        return {"fundamental_value": self._current_value, "mispricing": diff, "mispricing_pct": pct}

    def describe(self) -> Dict:
        return {
            "enabled": self.config.enabled,
            "r_bar": self.config.r_bar,
            "kappa": self.config.kappa,
            "sigma_s": self.config.sigma_s,
            "current_value": self._current_value,
            "time": self._time,
            "replay_mode": bool(self.config.replay_path),
        }

    def get_recent_history(self, n: int = 100) -> List[float]:
        return self._history[-n:]
