"""Training utilities for the combined DARL + indicator-driven intraday RL system."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd
from stable_baselines3 import DQN, PPO
from stable_baselines3.common.callbacks import BaseCallback, CallbackList
from stable_baselines3.common.vec_env import DummyVecEnv

from .environment import IntradayEnvConfig, IntradayTradingEnv
from .features import MinuteDataAugmenter, build_intraday_features, load_ohlcv_csv, split_sessions


@dataclass
class PPOTrainingConfig:
    """PPO setup tuned for minute-bar intraday learning."""

    total_timesteps: int = 250_000
    learning_rate: float = 3e-4
    n_steps: int = 1024
    batch_size: int = 256
    gamma: float = 0.995
    gae_lambda: float = 0.97
    clip_range: float = 0.2
    ent_coef: float = 0.005
    vf_coef: float = 0.5
    net_arch: tuple[int, int] = (256, 256)
    tensorboard_log: str | None = "./tensorboard_logs/intraday_ppo"


@dataclass
class DQNTrainingConfig:
    """Optional baseline for PPO comparison."""

    total_timesteps: int = 250_000
    learning_rate: float = 1e-4
    buffer_size: int = 100_000
    batch_size: int = 256
    gamma: float = 0.995
    exploration_fraction: float = 0.15
    exploration_final_eps: float = 0.05
    target_update_interval: int = 2000
    net_arch: tuple[int, int] = (256, 256)
    tensorboard_log: str | None = "./tensorboard_logs/intraday_dqn"


class PeriodicCheckpointCallback(BaseCallback):
    """Saves model checkpoint every N steps during training."""

    def __init__(self, checkpoint_dir: str | Path, save_freq: int = 50_000, verbose: int = 0):
        super().__init__(verbose)
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.save_freq = save_freq
        self.last_save_step = 0

    def _on_step(self) -> bool:
        if self.num_timesteps - self.last_save_step >= self.save_freq:
            checkpoint_path = self.checkpoint_dir / f"checkpoint_{self.num_timesteps}"
            self.model.save(str(checkpoint_path))
            _update_latest_model_alias(checkpoint_path, self.checkpoint_dir)
            if self.verbose > 0:
                print(f"\n✅ Checkpoint saved: {checkpoint_path.name}")
            self.last_save_step = self.num_timesteps
        return True


def _resolve_model_file(path: str | Path) -> Path | None:
    resolved = Path(path)
    if resolved.exists():
        return resolved
    zip_path = resolved.with_suffix(".zip")
    if zip_path.exists():
        return zip_path
    return None


def _find_latest_checkpoint(checkpoint_dir: str | Path | None) -> Path | None:
    if not checkpoint_dir:
        return None
    checkpoint_root = Path(checkpoint_dir)
    if not checkpoint_root.exists():
        return None
    candidates = sorted(
        checkpoint_root.glob("checkpoint_*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _update_latest_model_alias(source_path: str | Path, checkpoint_dir: str | Path | None) -> None:
    if not checkpoint_dir:
        return
    checkpoint_root = Path(checkpoint_dir)
    resolved = _resolve_model_file(source_path)
    if resolved is None:
        return
    latest_path = checkpoint_root / "latest_model.zip"
    shutil.copy2(resolved, latest_path)


def prepare_training_sessions(
    csv_path: str,
    apply_augmentation: bool = True,
    copies_per_session: int = 1,
    augment_seed: int = 42,
) -> List[pd.DataFrame]:
    """Load minute OHLCV and create feature-rich training sessions."""
    raw = load_ohlcv_csv(csv_path)
    featured = build_intraday_features(raw)
    sessions = split_sessions(featured)

    if apply_augmentation:
        augmenter = MinuteDataAugmenter(seed=augment_seed)
        sessions = augmenter.augment_sessions(sessions, copies_per_session=copies_per_session)

    return sessions


def train_ppo(
    sessions: Sequence[pd.DataFrame],
    env_config: IntradayEnvConfig,
    train_config: PPOTrainingConfig,
    model_output_path: str,
    checkpoint_dir: str | Path | None = None,
    checkpoint_save_freq: int = 50_000,
    resume: bool = True,
) -> PPO:
    """Train PPO as the primary policy for constrained morning-session trading.
    
    Supports automatic checkpoint resumption: if model exists, continues training.
    Checkpoints are saved periodically to enable resumption on interruption.
    
    Args:
        sessions: Training data sessions
        env_config: Environment configuration
        train_config: PPO training configuration
        model_output_path: Final model save path
        checkpoint_dir: Directory for periodic checkpoints (optional)
        checkpoint_save_freq: Save checkpoint every N timesteps
    
    Returns:
        Trained PPO model
    """
    vec_env = DummyVecEnv([lambda: IntradayTradingEnv(sessions=sessions, config=env_config)])

    policy_kwargs = {"net_arch": list(train_config.net_arch)}
    
    resume_path = None
    if resume:
        resume_path = _resolve_model_file(model_output_path)
        if resume_path is None:
            resume_path = _find_latest_checkpoint(checkpoint_dir)

    if resume_path is not None:
        print(f"📂 Loading existing model from {resume_path} to resume training...")
        model = PPO.load(str(resume_path), env=vec_env, verbose=1)
        total_steps_to_learn = train_config.total_timesteps
        print(
            f"   Resuming from step {model.num_timesteps}. Additional: {total_steps_to_learn:,} timesteps"
        )
    else:
        print(f"🚀 Creating new PPO model...")
        model = PPO(
            policy="MlpPolicy",
            env=vec_env,
            learning_rate=train_config.learning_rate,
            n_steps=train_config.n_steps,
            batch_size=train_config.batch_size,
            gamma=train_config.gamma,
            gae_lambda=train_config.gae_lambda,
            clip_range=train_config.clip_range,
            ent_coef=train_config.ent_coef,
            vf_coef=train_config.vf_coef,
            policy_kwargs=policy_kwargs,
            tensorboard_log=train_config.tensorboard_log,
            verbose=1,
        )
        total_steps_to_learn = train_config.total_timesteps

    # Setup checkpoint callback
    callbacks = []
    if checkpoint_dir:
        checkpoint_callback = PeriodicCheckpointCallback(
            checkpoint_dir=checkpoint_dir,
            save_freq=checkpoint_save_freq,
            verbose=1
        )
        callbacks.append(checkpoint_callback)
        print(f"💾 Periodic checkpoints enabled: every {checkpoint_save_freq:,} steps → {checkpoint_dir}")

    callback_list = CallbackList(callbacks) if callbacks else None

    # Train (or continue training)
    model.learn(
        total_timesteps=total_steps_to_learn,
        callback=callback_list,
        reset_num_timesteps=False  # Important: continue timestep counter
    )

    # Save final model
    model_path = Path(model_output_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(model_output_path)
    _update_latest_model_alias(model_path, checkpoint_dir)
    print(f"✅ Model training complete. Final model saved → {model_output_path}")
    
    return model


def train_dqn_baseline(
    sessions: Sequence[pd.DataFrame],
    env_config: IntradayEnvConfig,
    train_config: DQNTrainingConfig,
    model_output_path: str,
    checkpoint_dir: str | Path | None = None,
    checkpoint_save_freq: int = 50_000,
    resume: bool = True,
) -> DQN:
    """Optional DQN baseline to compare against PPO in the same environment.
    
    Supports automatic checkpoint resumption: if model exists, continues training.
    Checkpoints are saved periodically to enable resumption on interruption.
    
    Args:
        sessions: Training data sessions
        env_config: Environment configuration
        train_config: DQN training configuration
        model_output_path: Final model save path
        checkpoint_dir: Directory for periodic checkpoints (optional)
        checkpoint_save_freq: Save checkpoint every N timesteps
    
    Returns:
        Trained DQN model
    """
    vec_env = DummyVecEnv([lambda: IntradayTradingEnv(sessions=sessions, config=env_config)])

    policy_kwargs = {"net_arch": list(train_config.net_arch)}
    
    resume_path = None
    if resume:
        resume_path = _resolve_model_file(model_output_path)
        if resume_path is None:
            resume_path = _find_latest_checkpoint(checkpoint_dir)

    if resume_path is not None:
        print(f"📂 Loading existing model from {resume_path} to resume training...")
        model = DQN.load(str(resume_path), env=vec_env, verbose=1)
        total_steps_to_learn = train_config.total_timesteps
        print(
            f"   Resuming from step {model.num_timesteps}. Additional: {total_steps_to_learn:,} timesteps"
        )
    else:
        print(f"🚀 Creating new DQN model...")
        model = DQN(
            policy="MlpPolicy",
            env=vec_env,
            learning_rate=train_config.learning_rate,
            buffer_size=train_config.buffer_size,
            batch_size=train_config.batch_size,
            gamma=train_config.gamma,
            exploration_fraction=train_config.exploration_fraction,
            exploration_final_eps=train_config.exploration_final_eps,
            target_update_interval=train_config.target_update_interval,
            policy_kwargs=policy_kwargs,
            tensorboard_log=train_config.tensorboard_log,
            verbose=1,
        )
        total_steps_to_learn = train_config.total_timesteps

    # Setup checkpoint callback
    callbacks = []
    if checkpoint_dir:
        checkpoint_callback = PeriodicCheckpointCallback(
            checkpoint_dir=checkpoint_dir,
            save_freq=checkpoint_save_freq,
            verbose=1
        )
        callbacks.append(checkpoint_callback)
        print(f"💾 Periodic checkpoints enabled: every {checkpoint_save_freq:,} steps → {checkpoint_dir}")

    callback_list = CallbackList(callbacks) if callbacks else None

    # Train (or continue training)
    model.learn(
        total_timesteps=total_steps_to_learn,
        callback=callback_list,
        reset_num_timesteps=False  # Important: continue timestep counter
    )

    # Save final model
    model_path = Path(model_output_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(model_output_path)
    _update_latest_model_alias(model_path, checkpoint_dir)
    print(f"✅ Model training complete. Final model saved → {model_output_path}")
    
    return model


def load_and_prepare_sessions(csv_path: str) -> List[pd.DataFrame]:
    """Helper for inference/backtesting preparation from plain OHLCV CSV."""
    raw = load_ohlcv_csv(csv_path)
    featured = build_intraday_features(raw)
    return split_sessions(featured)


def describe_training_setup(env_config: IntradayEnvConfig, ppo_config: PPOTrainingConfig) -> Dict[str, float | int]:
    """Return a machine-readable summary of key implementation parameters."""
    state_size = env_config.lookback * 5 + 6
    return {
        "state_size": state_size,
        "action_space": 3,
        "lookback": env_config.lookback,
        "morning_minutes": env_config.morning_minutes,
        "lot_size": env_config.lot_size,
        "transaction_cost_bps": env_config.transaction_cost_bps,
        "ppo_total_timesteps": ppo_config.total_timesteps,
        "ppo_learning_rate": ppo_config.learning_rate,
        "ppo_n_steps": ppo_config.n_steps,
        "ppo_batch_size": ppo_config.batch_size,
    }
