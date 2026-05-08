#!/usr/bin/env python3
"""Backtest trained intraday RL policy on 1m/5m/15m OHLCV data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from stable_baselines3 import DQN, PPO

from src.prediction.intraday_rl.backtest import backtest_model
from src.prediction.intraday_rl.environment import IntradayEnvConfig
from src.prediction.intraday_rl.features import build_intraday_features, load_ohlcv_csv, resample_ohlcv, split_sessions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest trained intraday RL policy")
    parser.add_argument("--csv", type=str, required=True, help="Path to OHLCV CSV")
    parser.add_argument("--model", type=str, required=True, help="Path to saved PPO/DQN model")
    parser.add_argument("--algo", type=str, default="ppo", choices=["ppo", "dqn"])
    parser.add_argument("--timeframe", type=str, default="5min", choices=["1min", "5min", "15min"])
    parser.add_argument("--lookback", type=int, default=30)
    parser.add_argument("--morning-minutes", type=int, default=60)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    raw = load_ohlcv_csv(args.csv)
    featured = build_intraday_features(raw)

    # DARL transfer: policy trained at 1m can be evaluated at higher execution bars.
    transformed = resample_ohlcv(featured, timeframe=args.timeframe)
    sessions = split_sessions(transformed)

    env_config = IntradayEnvConfig(
        lookback=args.lookback,
        morning_minutes=args.morning_minutes,
        random_reset=False,
    )

    if args.algo == "ppo":
        model = PPO.load(args.model)
    else:
        model = DQN.load(args.model)

    report = backtest_model(model=model, sessions=sessions, env_config=env_config)
    print(json.dumps(report["summary"], indent=2))

    # Print top 5 worst sessions for quick debugging.
    worst = sorted(report["session_results"], key=lambda x: x["return_pct"])[:5]
    print("\nWorst sessions:")
    print(json.dumps(worst, indent=2))


if __name__ == "__main__":
    main()
