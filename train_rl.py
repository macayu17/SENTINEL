"""Train a PPO market-making policy for SENTINEL."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CallbackList, CheckpointCallback, EvalCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
import torch.nn as nn

from backend.src.market.training_setup import create_market_maker_env


class MetricsLoggerCallback(BaseCallback):
    """Track the market-maker's training health in TensorBoard."""

    def __init__(self, verbose: int = 0) -> None:
        super().__init__(verbose)
        self.episode_rewards: list[float] = []
        self.pnls: list[float] = []
        self.inventories: list[float] = []
        self.drawdowns: list[float] = []
        self.fill_rates: list[float] = []

    def _on_step(self) -> bool:
        infos = self.locals.get("infos", [])
        rewards = self.locals.get("rewards")
        dones = self.locals.get("dones")

        if rewards is not None:
            self.episode_rewards.append(float(rewards[0]))

        for info in infos:
            if not info:
                continue
            self.pnls.append(float(info.get("pnl", 0.0)))
            self.inventories.append(abs(float(info.get("inventory", 0.0))))
            self.drawdowns.append(float(info.get("drawdown", 0.0)))
            self.fill_rates.append(float(info.get("fill_rate", 0.0)))

        if dones is not None and bool(dones[0]) and self.pnls:
            pnl_series = np.asarray(self.pnls, dtype=float)
            reward_total = float(np.sum(self.episode_rewards))
            drawdown_series = np.maximum.accumulate(pnl_series) - pnl_series
            returns = np.diff(pnl_series) if len(pnl_series) > 1 else np.array([0.0])
            sharpe_like = float((returns.mean() / (returns.std() + 1e-8)) * np.sqrt(252))

            self.logger.record("market_maker/final_pnl", float(self.pnls[-1]))
            self.logger.record("market_maker/mean_abs_inventory", float(np.mean(self.inventories)))
            self.logger.record("market_maker/max_drawdown", float(np.max(drawdown_series)))
            self.logger.record("market_maker/cumulative_reward", reward_total)
            self.logger.record("market_maker/avg_fill_rate", float(np.mean(self.fill_rates)))
            self.logger.record("market_maker/sharpe_like", sharpe_like)

            self.episode_rewards.clear()
            self.pnls.clear()
            self.inventories.clear()
            self.drawdowns.clear()
            self.fill_rates.clear()

        return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a PPO market-making policy")
    parser.add_argument("--timesteps", type=int, default=60_000)
    parser.add_argument("--duration-seconds", type=int, default=1_000)
    parser.add_argument("--initial-price", type=float, default=100.0)
    parser.add_argument("--learning-rate", type=float, default=2.5e-4)
    parser.add_argument("--n-steps", type=int, default=2_048)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--n-envs", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--save-path", type=str, default="backend/models/ppo_market_maker")
    parser.add_argument("--tensorboard-log", type=str, default="tensorboard_logs")
    parser.add_argument("--eval-freq", type=int, default=10_000)
    return parser.parse_args()


def make_env_factory(args: argparse.Namespace, rank: int):
    def _factory():
        env = create_market_maker_env(
            initial_price=args.initial_price,
            duration_seconds=args.duration_seconds,
        )
        env.reset(seed=args.seed + rank)
        return Monitor(env)

    return _factory


def train(args: argparse.Namespace) -> None:
    os.makedirs(Path(args.save_path).parent, exist_ok=True)
    os.makedirs(args.tensorboard_log, exist_ok=True)

    train_env = DummyVecEnv([make_env_factory(args, rank) for rank in range(args.n_envs)])
    eval_env = DummyVecEnv([make_env_factory(args, 10_000)])

    train_env = VecNormalize(train_env, norm_obs=True, norm_reward=True, clip_obs=10.0)
    eval_env = VecNormalize(eval_env, norm_obs=True, norm_reward=False, clip_obs=10.0, training=False)

    policy_kwargs = {
        "activation_fn": nn.Tanh,
        "net_arch": {"pi": [128, 128], "vf": [128, 128]},
    }

    model = PPO(
        "MlpPolicy",
        train_env,
        verbose=1,
        learning_rate=args.learning_rate,
        n_steps=args.n_steps,
        batch_size=args.batch_size,
        gamma=0.995,
        gae_lambda=0.98,
        ent_coef=0.01,
        clip_range=0.2,
        vf_coef=0.5,
        max_grad_norm=0.5,
        tensorboard_log=args.tensorboard_log,
        policy_kwargs=policy_kwargs,
        seed=args.seed,
        device="cpu",
    )

    checkpoint_callback = CheckpointCallback(
        save_freq=max(1, args.eval_freq // max(1, args.n_envs)),
        save_path=str(Path(args.save_path).parent / "checkpoints"),
        name_prefix="ppo_market_maker",
    )
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=str(Path(args.save_path).parent / "best_model"),
        log_path=str(Path(args.save_path).parent / "eval_logs"),
        eval_freq=max(1, args.eval_freq // max(1, args.n_envs)),
        deterministic=True,
        render=False,
    )
    metrics_callback = MetricsLoggerCallback()

    model.learn(
        total_timesteps=args.timesteps,
        callback=CallbackList([checkpoint_callback, eval_callback, metrics_callback]),
        progress_bar=True,
    )

    model.save(args.save_path)
    train_env.save(f"{args.save_path}.vecnormalize.pkl")
    print(f"Saved PPO model to {args.save_path}.zip")


if __name__ == "__main__":
    train(parse_args())
