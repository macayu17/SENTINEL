#!/usr/bin/env python3
"""Train the combined DARL + indicator intraday RL system."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.prediction.intraday_rl.environment import IntradayEnvConfig
from src.prediction.intraday_rl.trainer import (
    DQNTrainingConfig,
    PPOTrainingConfig,
    describe_training_setup,
    prepare_training_sessions,
    train_dqn_baseline,
    train_ppo,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train intraday PPO policy on minute OHLCV")
    parser.add_argument("--csv", type=str, required=True, help="Path to minute OHLCV CSV")
    parser.add_argument(
        "--output-model",
        type=str,
        default=str(Path(__file__).parent.parent / "models" / "intraday_ppo"),
        help="Output path for PPO model",
    )
    parser.add_argument("--total-timesteps", type=int, default=250000)
    parser.add_argument("--lookback", type=int, default=30)
    parser.add_argument("--morning-minutes", type=int, default=60)
    parser.add_argument("--copies-per-session", type=int, default=1)
    parser.add_argument("--disable-augmentation", action="store_true")
    parser.add_argument("--train-dqn-baseline", action="store_true")
    parser.add_argument(
        "--dqn-output-model",
        type=str,
        default=str(Path(__file__).parent.parent / "models" / "intraday_dqn"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    sessions = prepare_training_sessions(
        csv_path=args.csv,
        apply_augmentation=not args.disable_augmentation,
        copies_per_session=args.copies_per_session,
    )

    env_config = IntradayEnvConfig(
        lookback=args.lookback,
        morning_minutes=args.morning_minutes,
    )

    ppo_config = PPOTrainingConfig(total_timesteps=args.total_timesteps)

    setup = describe_training_setup(env_config, ppo_config)
    print("Training setup:\n" + json.dumps(setup, indent=2))
    print(f"Number of sessions used for training: {len(sessions)}")

    model = train_ppo(
        sessions=sessions,
        env_config=env_config,
        train_config=ppo_config,
        model_output_path=args.output_model,
    )
    print(f"PPO model saved to: {args.output_model}")

    if args.train_dqn_baseline:
        dqn_cfg = DQNTrainingConfig(total_timesteps=args.total_timesteps)
        train_dqn_baseline(
            sessions=sessions,
            env_config=env_config,
            train_config=dqn_cfg,
            model_output_path=args.dqn_output_model,
        )
        print(f"DQN baseline saved to: {args.dqn_output_model}")

    # Keep a direct operational reminder from DARL transfer strategy.
    print("\nDeployment reminder:")
    print("1) Train on 1-minute bars (maximum sample density).")
    print("2) Deploy same policy on 5-minute or 15-minute bars for smoother execution.")
    print("3) Recompute SMA/RSI/ATV after resampling to preserve feature meaning.")

    _ = model


if __name__ == "__main__":
    main()
