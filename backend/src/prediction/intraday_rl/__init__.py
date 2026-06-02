"""Intraday RL package combining indicator features and data-augmentation RL."""

from importlib import import_module
from typing import Any

from .backtest import backtest_model
from .environment import (
    ACTION_BUY,
    ACTION_HOLD,
    ACTION_SELL,
    IntradayEnvConfig,
    IntradayTradingEnv,
)
from .features import (
    MinuteDataAugmenter,
    build_intraday_features,
    load_ohlcv_csv,
    resample_ohlcv,
    split_sessions,
)

_TRAINER_EXPORTS = {
    "DQNTrainingConfig",
    "PPOTrainingConfig",
    "describe_training_setup",
    "load_and_prepare_sessions",
    "prepare_training_sessions",
    "train_dqn_baseline",
    "train_ppo",
}


def __getattr__(name: str) -> Any:
    if name in _TRAINER_EXPORTS:
        trainer = import_module(f"{__name__}.trainer")
        value = getattr(trainer, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "ACTION_BUY",
    "ACTION_HOLD",
    "ACTION_SELL",
    "IntradayEnvConfig",
    "IntradayTradingEnv",
    "MinuteDataAugmenter",
    "build_intraday_features",
    "load_ohlcv_csv",
    "resample_ohlcv",
    "split_sessions",
    "PPOTrainingConfig",
    "DQNTrainingConfig",
    "describe_training_setup",
    "prepare_training_sessions",
    "load_and_prepare_sessions",
    "train_ppo",
    "train_dqn_baseline",
    "backtest_model",
]
