"""Feature engineering and data utilities for intraday RL trading."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

import numpy as np
import pandas as pd


REQUIRED_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def ensure_ohlcv_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Validate OHLCV schema and return a timestamp-indexed copy."""
    working = df.copy()

    if "timestamp" in working.columns:
        working["timestamp"] = pd.to_datetime(working["timestamp"])
        working = working.sort_values("timestamp").set_index("timestamp")
    elif not isinstance(working.index, pd.DatetimeIndex):
        raise ValueError(
            "DataFrame must have either a 'timestamp' column or a DatetimeIndex."
        )

    missing = [col for col in REQUIRED_OHLCV_COLUMNS if col not in working.columns]
    if missing:
        raise ValueError(f"Missing OHLCV columns: {missing}")

    # Keep only finite numeric rows to avoid NaN propagation in indicators.
    working = working.replace([np.inf, -np.inf], np.nan).dropna(
        subset=list(REQUIRED_OHLCV_COLUMNS)
    )

    return working


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Classic Wilder RSI implementation."""
    delta = close.diff().fillna(0.0)
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0).clip(0.0, 100.0)


def build_intraday_features(
    raw_df: pd.DataFrame,
    sma_short_window: int = 9,
    sma_long_window: int = 21,
    rsi_period: int = 14,
    atv_window: int = 20,
) -> pd.DataFrame:
    """Build SMA/ATV/RSI features used by the RL policy as model inputs."""
    df = ensure_ohlcv_schema(raw_df)

    df["sma_short"] = df["close"].rolling(sma_short_window, min_periods=1).mean()
    df["sma_long"] = df["close"].rolling(sma_long_window, min_periods=1).mean()
    df["sma_signal"] = np.sign(df["sma_short"] - df["sma_long"]).astype(float)

    df["atv"] = df["volume"].rolling(atv_window, min_periods=1).mean()
    df["volume_ratio"] = (df["volume"] / df["atv"].replace(0.0, np.nan)).fillna(1.0)

    df["rsi"] = compute_rsi(df["close"], period=rsi_period)
    df["returns_1m"] = df["close"].pct_change().fillna(0.0)

    return df


def split_sessions(feature_df: pd.DataFrame) -> List[pd.DataFrame]:
    """Split a timestamp-indexed dataframe into per-day sessions."""
    if not isinstance(feature_df.index, pd.DatetimeIndex):
        raise ValueError("feature_df must use a DatetimeIndex")

    sessions: List[pd.DataFrame] = []
    for _, group in feature_df.groupby(feature_df.index.date):
        if len(group) > 30:
            sessions.append(group.copy())
    return sessions


def resample_ohlcv(feature_df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample intraday OHLCV to a higher timeframe for policy deployment."""
    if timeframe not in {"1min", "5min", "15min"}:
        raise ValueError("timeframe must be one of: 1min, 5min, 15min")

    if timeframe == "1min":
        return feature_df.copy()

    rule = "5min" if timeframe == "5min" else "15min"
    resampled = (
        feature_df.resample(rule)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
    )

    # Recompute indicators on the deployed timeframe to keep feature semantics consistent.
    return build_intraday_features(resampled)


@dataclass
class MinuteDataAugmenter:
    """Data augmentation inspired by DARL for more robust policy learning."""

    price_noise_std: float = 0.0008
    volume_noise_std: float = 0.03
    seed: int | None = 42

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def augment_session(self, session_df: pd.DataFrame) -> pd.DataFrame:
        """Create a synthetic minute-level session while preserving OHLC structure."""
        df = session_df.copy()

        # Jitter close, then reconstruct open/high/low around it.
        close_noise = self._rng.normal(0.0, self.price_noise_std, len(df))
        vol_noise = self._rng.normal(0.0, self.volume_noise_std, len(df))

        df["close"] = (df["close"] * (1.0 + close_noise)).clip(lower=0.01)
        df["open"] = df["close"].shift(1).fillna(df["open"])

        high_jitter = np.abs(self._rng.normal(0.0, self.price_noise_std * 2.0, len(df)))
        low_jitter = np.abs(self._rng.normal(0.0, self.price_noise_std * 2.0, len(df)))

        df["high"] = np.maximum(df[["open", "close"]].max(axis=1), df["high"] * (1.0 + high_jitter))
        df["low"] = np.minimum(df[["open", "close"]].min(axis=1), df["low"] * (1.0 - low_jitter))
        df["volume"] = (df["volume"] * (1.0 + vol_noise)).clip(lower=1.0)

        return build_intraday_features(df)

    def augment_sessions(
        self,
        sessions: Sequence[pd.DataFrame],
        copies_per_session: int = 1,
    ) -> List[pd.DataFrame]:
        """Append augmented copies to original sessions for training-time diversification."""
        output: List[pd.DataFrame] = list(sessions)
        for session in sessions:
            for _ in range(copies_per_session):
                output.append(self.augment_session(session))
        return output


def load_ohlcv_csv(csv_path: str) -> pd.DataFrame:
    """Load OHLCV CSV and return a timestamp-indexed DataFrame."""
    df = pd.read_csv(csv_path)
    return ensure_ohlcv_schema(df)
