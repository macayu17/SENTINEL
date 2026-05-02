#!/usr/bin/env python3
"""
Comprehensive RL Training + Backtesting + Checkpoint System for Intraday Trading

Features:
  - Model checkpoint management with best model tracking
  - Training progress resumption from checkpoints
  - Parameter sweep with progress persistence
  - Detailed backtest metrics (Sharpe, max drawdown, profit factor, etc.)
  - Performance comparison across configurations
  - Tensorboard integration
  - Detailed logging to files
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from stable_baselines3 import DQN, PPO

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.prediction.intraday_rl.backtest import backtest_model
from src.prediction.intraday_rl.environment import IntradayEnvConfig, IntradayTradingEnv
from src.prediction.intraday_rl.features import (
    MinuteDataAugmenter,
    build_intraday_features,
    load_ohlcv_csv,
    resample_ohlcv,
    split_sessions,
)
from src.prediction.intraday_rl.trainer import (
    DQNTrainingConfig,
    PPOTrainingConfig,
    describe_training_setup,
    prepare_training_sessions,
    train_dqn_baseline,
    train_ppo,
)
from stable_baselines3.common.vec_env import DummyVecEnv


def resolve_model_path(model_path: str | Path) -> Path:
    candidate = Path(model_path)
    tried: List[Path] = []

    if candidate.is_dir():
        for name in ("latest_model.zip", "best_model.zip"):
            path = candidate / name
            tried.append(path)
            if path.exists():
                return path

    tried.append(candidate)
    if candidate.exists():
        return candidate

    zip_path = candidate.with_suffix(".zip")
    tried.append(zip_path)
    if zip_path.exists():
        return zip_path

    tried_paths = ", ".join(str(path) for path in tried)
    raise FileNotFoundError(f"Model not found. Tried: {tried_paths}")


# ============================================================
#                   CHECKPOINT MANAGER
# ============================================================


class CheckpointManager:
    """Manages model checkpoints, best models, and metadata."""

    def __init__(self, checkpoint_dir: str | Path):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.checkpoint_dir / "checkpoint_metadata.json"
        self.best_models_file = self.checkpoint_dir / "best_models.json"

    def get_metadata(self) -> Dict[str, Any]:
        """Load checkpoint metadata."""
        if self.metadata_file.exists():
            with open(self.metadata_file) as f:
                return json.load(f)
        return {"checkpoints": {}, "last_updated": None}

    def save_metadata(self, metadata: Dict[str, Any]) -> None:
        """Save checkpoint metadata."""
        metadata["last_updated"] = datetime.now().isoformat()
        with open(self.metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

    def save_checkpoint(
        self,
        model_name: str,
        model_path: str | Path,
        metrics: Dict[str, float],
        config: Dict[str, Any],
        epoch: int,
    ) -> None:
        """Save model checkpoint with metrics."""
        metadata = self.get_metadata()

        # Create checkpoint entry
        checkpoint_key = f"{model_name}_epoch_{epoch}"
        metadata["checkpoints"][checkpoint_key] = {
            "model_path": str(model_path),
            "epoch": epoch,
            "metrics": metrics,
            "config": config,
            "timestamp": datetime.now().isoformat(),
        }

        self.save_metadata(metadata)

    def get_best_model(self, model_name: str, metric: str = "total_return") -> Optional[Dict[str, Any]]:
        """Get best checkpoint by metric."""
        metadata = self.get_metadata()
        checkpoints = [cp for name, cp in metadata["checkpoints"].items() if model_name in name]

        if not checkpoints:
            return None

        best = max(checkpoints, key=lambda x: x["metrics"].get(metric, -np.inf))
        return best

    def save_best_model_info(self, model_name: str, best_info: Dict[str, Any]) -> None:
        """Save best model information."""
        best_models = {}
        if self.best_models_file.exists():
            with open(self.best_models_file) as f:
                best_models = json.load(f)

        best_models[model_name] = {
            **best_info,
            "timestamp": datetime.now().isoformat(),
        }

        with open(self.best_models_file, "w") as f:
            json.dump(best_models, f, indent=2)


# ============================================================
#                   TRAINING ORCHESTRATOR
# ============================================================


@dataclass
class TrainingResult:
    """Result of a single training run."""

    config_name: str
    algorithm: str
    model_path: str
    metrics: Dict[str, float]
    total_timesteps: int
    training_time: float


class RLTrainingOrchestrator:
    """Orchestrates training with checkpointing and best model tracking."""

    def __init__(
        self,
        csv_path: str,
        output_dir: str = "./models/rl_training",
        results_dir: str = "./results/rl_training",
        checkpoint_dir: str = "./checkpoints/rl_training",
        augment: bool = True,
        augment_copies: int = 1,
    ):
        self.csv_path = csv_path
        self.output_dir = Path(output_dir)
        self.results_dir = Path(results_dir)
        self.checkpoint_dir = CheckpointManager(checkpoint_dir)

        # Setup directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Load sessions once
        print("📊 Loading and preparing training data...")
        self.sessions = prepare_training_sessions(
            csv_path=csv_path,
            apply_augmentation=augment,
            copies_per_session=augment_copies,
        )
        print(f"✅ Loaded {len(self.sessions)} sessions")

    def train_single(
        self,
        config_name: str,
        algorithm: str,
        env_config: IntradayEnvConfig,
        train_config: PPOTrainingConfig | DQNTrainingConfig,
        resume_from: Optional[str] = None,
    ) -> TrainingResult:
        """Train a single model with automatic checkpoint resumption."""
        print(f"\n{'─'*70}")
        print(f"  🚀 Training: {config_name}")
        print(f"     Algorithm: {algorithm.upper()}")
        print(f"     Timesteps: {train_config.total_timesteps:,}")
        print(f"{'─'*70}")

        model_path = self.output_dir / f"{config_name}_{algorithm}"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Setup checkpoint directory for this model
        model_checkpoint_dir = self.checkpoint_dir.checkpoint_dir / f"{config_name}_{algorithm}"

        start_time = datetime.now()

        try:
            if algorithm == "ppo":
                model = train_ppo(
                    sessions=self.sessions,
                    env_config=env_config,
                    train_config=train_config,
                    model_output_path=str(model_path),
                    checkpoint_dir=str(model_checkpoint_dir),
                    checkpoint_save_freq=50_000,
                )
            elif algorithm == "dqn":
                model = train_dqn_baseline(
                    sessions=self.sessions,
                    env_config=env_config,
                    train_config=train_config,
                    model_output_path=str(model_path),
                    checkpoint_dir=str(model_checkpoint_dir),
                    checkpoint_save_freq=50_000,
                )
            else:
                raise ValueError(f"Unknown algorithm: {algorithm}")

            elapsed = (datetime.now() - start_time).total_seconds()

            print(f"✅ Training complete in {elapsed:.1f}s")
            print(f"   Model saved → {model_path}")

            # Get setup description for metrics
            setup = describe_training_setup(env_config, train_config)

            result = TrainingResult(
                config_name=config_name,
                algorithm=algorithm,
                model_path=str(model_path),
                metrics=setup,
                total_timesteps=train_config.total_timesteps,
                training_time=elapsed,
            )

            # Save checkpoint
            self.checkpoint_dir.save_checkpoint(
                model_name=config_name,
                model_path=model_path,
                metrics=setup,
                config=vars(train_config),
                epoch=1,
            )

            return result

        except Exception as e:
            print(f"❌ Training failed: {e}")
            import traceback

            traceback.print_exc()
            raise

    def backtest_model(
        self,
        model_path: str | Path,
        algorithm: str,
        env_config: IntradayEnvConfig,
        timeframe: str = "5min",
    ) -> Dict[str, Any]:
        """Backtest a trained model."""
        resolved_model_path = resolve_model_path(model_path)
        print(f"\n  📈 Backtesting: {resolved_model_path.name}")

        # Load and resample data
        raw = load_ohlcv_csv(self.csv_path)
        featured = build_intraday_features(raw)
        transformed = resample_ohlcv(featured, timeframe=timeframe)
        sessions = split_sessions(transformed)

        # Load model
        if algorithm == "ppo":
            model = PPO.load(str(resolved_model_path))
        elif algorithm == "dqn":
            model = DQN.load(str(resolved_model_path))
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")

        # Run backtest
        env_config_copy = IntradayEnvConfig(
            lookback=env_config.lookback,
            initial_cash=env_config.initial_cash,
            lot_size=env_config.lot_size,
            transaction_cost_bps=env_config.transaction_cost_bps,
            trailing_stop_pct=env_config.trailing_stop_pct,
            trend_bonus=env_config.trend_bonus,
            volume_bonus=env_config.volume_bonus,
            invalid_action_penalty=env_config.invalid_action_penalty,
            volume_confirmation_multiplier=env_config.volume_confirmation_multiplier,
            morning_minutes=env_config.morning_minutes,
            random_reset=False,
            reward_scale=env_config.reward_scale,
        )

        report = backtest_model(model=model, sessions=sessions, env_config=env_config_copy)
        return report


# ============================================================
#                   METRICS CALCULATOR
# ============================================================


def calculate_backtest_metrics(report: Dict[str, Any]) -> Dict[str, float]:
    """Extract and calculate performance metrics from backtest report."""
    summary = report.get("summary", {})
    session_results = report.get("session_results", [])

    if not session_results:
        return {
            "avg_return": 0.0,
            "total_return": 0.0,
            "win_rate": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "profit_factor": 0.0,
        }

    returns = [s.get("return_pct", 0.0) for s in session_results]
    wins = sum(1 for r in returns if r > 0)
    losses = sum(1 for r in returns if r < 0)

    # Calculate profit factor
    gross_profit = sum(r for r in returns if r > 0)
    gross_loss = abs(sum(r for r in returns if r < 0))
    profit_factor = gross_profit / max(gross_loss, 1.0)

    # Calculate Sharpe (simple approximation)
    returns_array = np.array(returns)
    sharpe = (returns_array.mean() / (returns_array.std() + 1e-8)) * np.sqrt(252)

    return {
        "avg_return": float(np.mean(returns)),
        "total_return": float(np.sum(returns)),
        "win_rate": float(wins / len(returns) * 100 if returns else 0),
        "sharpe": float(sharpe),
        "max_drawdown": float(summary.get("max_drawdown_pct", 0.0)),
        "profit_factor": float(profit_factor),
        "num_trades": int(sum(s.get("trade_count", 0) for s in session_results)),
    }


# ============================================================
#                   PARAMETER SWEEP
# ============================================================


def run_parameter_sweep(
    csv_path: str,
    output_dir: str = "./models/rl_sweep",
    results_dir: str = "./results/rl_sweep",
    checkpoint_dir: str = "./checkpoints/rl_sweep",
    force_fresh: bool = False,
) -> List[Dict[str, Any]]:
    """
    Sweep hyperparameters and track best models.
    Progress is checkpointed — can resume mid-sweep.
    """
    print("\n" + "=" * 80)
    print("RL HYPERPARAMETER SWEEP")
    print("=" * 80)

    # Define sweep ranges
    learning_rates = [1e-4, 3e-4, 1e-3]
    net_architectures = [(128, 128), (256, 256), (512, 512)]
    algorithms = ["ppo"]  # Can add "dqn" for comparison

    total_combos = len(learning_rates) * len(net_architectures) * len(algorithms)
    print(f"\n🔄 Total combinations: {total_combos}")

    checkpoint_mgr = CheckpointManager(checkpoint_dir)
    results_file = Path(results_dir) / f"sweep_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)

    # Load checkpoint if resuming
    checkpoint_path = Path(checkpoint_dir) / "sweep_checkpoint.json"
    completed_combos = []
    results_list = []

    if checkpoint_path.exists() and not force_fresh:
        print(f"📂 Resuming from checkpoint...")
        with open(checkpoint_path) as f:
            ckpt = json.load(f)
        completed_combos = ckpt.get("completed", [])
        results_list = ckpt.get("results", [])
        print(f"   ✅ {len(completed_combos)} combinations already done")
    elif force_fresh and checkpoint_path.exists():
        os.remove(checkpoint_path)
        print("🔄 Checkpoint cleared")

    orchestrator = RLTrainingOrchestrator(
        csv_path=csv_path,
        output_dir=output_dir,
        results_dir=results_dir,
        checkpoint_dir=checkpoint_dir,
        augment=True,
        augment_copies=1,
    )

    print(f"\n{'─'*80}")

    try:
        combo_idx = 0
        for algo in algorithms:
            for lr in learning_rates:
                for arch in net_architectures:
                    combo_idx += 1
                    combo_key = f"{algo}_lr{lr}_arch{arch}"

                    if combo_key in completed_combos:
                        print(f"   [{combo_idx}/{total_combos}] {combo_key} — ⏭️  SKIPPED (already done)")
                        continue

                    print(f"   [{combo_idx}/{total_combos}] {combo_key}...")

                    try:
                        # Create configs
                        env_config = IntradayEnvConfig(lookback=30, morning_minutes=60)
                        train_config = PPOTrainingConfig(
                            total_timesteps=100_000,
                            learning_rate=lr,
                            net_arch=arch,
                        )

                        # Train
                        train_result = orchestrator.train_single(
                            config_name=combo_key,
                            algorithm=algo,
                            env_config=env_config,
                            train_config=train_config,
                        )

                        # Backtest
                        backtest_report = orchestrator.backtest_model(
                            model_path=train_result.model_path,
                            algorithm=algo,
                            env_config=env_config,
                            timeframe="5min",
                        )

                        metrics = calculate_backtest_metrics(backtest_report)

                        result_entry = {
                            "combo": combo_key,
                            "algorithm": algo,
                            "learning_rate": lr,
                            "net_arch": arch,
                            **metrics,
                            "model_path": train_result.model_path,
                            "training_time": train_result.training_time,
                        }

                        results_list.append(result_entry)
                        completed_combos.append(combo_key)

                        print(f"      ✅ Return: {metrics['total_return']:+.2f}% | "
                              f"Sharpe: {metrics['sharpe']:.2f} | Win: {metrics['win_rate']:.1f}%")

                        # Save checkpoint
                        with open(checkpoint_path, "w") as f:
                            json.dump(
                                {"completed": completed_combos, "results": results_list},
                                f,
                                indent=2,
                            )

                    except Exception as e:
                        print(f"      ❌ Failed: {str(e)[:80]}")
                        continue

    except KeyboardInterrupt:
        print(f"\n\n⏸️  Paused. {len(completed_combos)}/{total_combos} done. Re-run to resume.\n")

    # Sort results by total return
    results_list.sort(key=lambda x: x["total_return"], reverse=True)

    # Print summary table
    print("\n" + "=" * 100)
    print("SWEEP RESULTS — RANKED BY TOTAL RETURN")
    print("=" * 100)
    print(
        f"{'Rank':<5} {'Algorithm':<8} {'Learning Rate':<15} {'Net Arch':<15} "
        f"{'Return %':<12} {'Win %':<10} {'Sharpe':<10} {'Max DD %':<10}"
    )
    print("─" * 100)

    for i, r in enumerate(results_list[:10], 1):
        print(
            f"{i:<5} {r['algorithm']:<8} {r['learning_rate']:<15.0e} {str(r['net_arch']):<15} "
            f"{r['total_return']:<12.2f} {r['win_rate']:<10.1f} {r['sharpe']:<10.2f} "
            f"{abs(r['max_drawdown']):<10.2f}"
        )
    print("─" * 100)

    # Save results
    with open(results_file, "w") as f:
        json.dump(results_list, f, indent=2)
    print(f"\n✅ Results saved → {results_file}")

    # Cleanup checkpoint
    if checkpoint_path.exists():
        os.remove(checkpoint_path)
        print("✅ Checkpoint cleaned up")

    return results_list


# ============================================================
#                   CLI & MAIN
# ============================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Comprehensive RL Training + Backtesting + Checkpoint System"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Train command
    train_parser = subparsers.add_parser("train", help="Train a single RL model")
    train_parser.add_argument("--csv", type=str, required=True, help="Path to OHLCV CSV")
    train_parser.add_argument("--name", type=str, default="ppo_intraday", help="Model name")
    train_parser.add_argument("--algo", type=str, default="ppo", choices=["ppo", "dqn"])
    train_parser.add_argument("--timesteps", type=int, default=250_000)
    train_parser.add_argument("--lr", type=float, default=3e-4, help="Learning rate")
    train_parser.add_argument("--net-arch", type=str, default="256,256", help="Network arch (comma-separated)")
    train_parser.add_argument(
        "--output-dir", type=str, default="./models/rl_training", help="Output directory"
    )
    train_parser.add_argument(
        "--results-dir", type=str, default="./results/rl_training", help="Results directory"
    )
    train_parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default="./checkpoints/rl_training",
        help="Checkpoint directory",
    )
    train_parser.add_argument("--no-augment", action="store_true", help="Disable data augmentation")
    train_parser.add_argument("--augment-copies", type=int, default=1)

    # Backtest command
    backtest_parser = subparsers.add_parser("backtest", help="Backtest trained model")
    backtest_parser.add_argument("--csv", type=str, required=True, help="Path to OHLCV CSV")
    backtest_parser.add_argument("--model", type=str, required=True, help="Path to model")
    backtest_parser.add_argument("--algo", type=str, default="ppo", choices=["ppo", "dqn"])
    backtest_parser.add_argument("--timeframe", type=str, default="5min", choices=["1min", "5min", "15min"])
    backtest_parser.add_argument(
        "--results-dir", type=str, default="./results/rl_backtest", help="Results directory"
    )

    # Sweep command
    sweep_parser = subparsers.add_parser("sweep", help="Hyperparameter sweep")
    sweep_parser.add_argument("--csv", type=str, required=True, help="Path to OHLCV CSV")
    sweep_parser.add_argument(
        "--output-dir", type=str, default="./models/rl_sweep", help="Output directory"
    )
    sweep_parser.add_argument(
        "--results-dir", type=str, default="./results/rl_sweep", help="Results directory"
    )
    sweep_parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default="./checkpoints/rl_sweep",
        help="Checkpoint directory",
    )
    sweep_parser.add_argument("--force-fresh", action="store_true", help="Clear and restart sweep")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.command:
        print("Usage: train_backtest_rl_system.py {train,backtest,sweep} [options]")
        return

    if args.command == "train":
        net_arch = tuple(map(int, args.net_arch.split(",")))

        orchestrator = RLTrainingOrchestrator(
            csv_path=args.csv,
            output_dir=args.output_dir,
            results_dir=args.results_dir,
            checkpoint_dir=args.checkpoint_dir,
            augment=not args.no_augment,
            augment_copies=args.augment_copies,
        )

        env_config = IntradayEnvConfig(lookback=30, morning_minutes=60)
        train_config = PPOTrainingConfig(
            total_timesteps=args.timesteps,
            learning_rate=args.lr,
            net_arch=net_arch,
        ) if args.algo == "ppo" else DQNTrainingConfig(
            total_timesteps=args.timesteps,
            learning_rate=args.lr,
            net_arch=net_arch,
        )

        result = orchestrator.train_single(
            config_name=args.name,
            algorithm=args.algo,
            env_config=env_config,
            train_config=train_config,
        )

        print(f"\n✅ Training complete!")
        print(f"   Model: {result.model_path}")
        print(f"   Time: {result.training_time:.1f}s")

    elif args.command == "backtest":
        orchestrator = RLTrainingOrchestrator(
            csv_path=args.csv,
            output_dir="./models",
            results_dir=args.results_dir,
        )

        env_config = IntradayEnvConfig(
            lookback=30, 
            morning_minutes=60,
            trend_bonus=0.002,
            volume_bonus=0.002,
            invalid_action_penalty=0.0001,
        )
        
        # Use 1min by default (same as training) unless specified
        timeframe = args.timeframe if args.timeframe != "5min" else "1min"
        
        report = orchestrator.backtest_model(
            model_path=args.model,
            algorithm=args.algo,
            env_config=env_config,
            timeframe=timeframe,
        )

        metrics = calculate_backtest_metrics(report)
        print("\nBacktest Summary:")
        print(json.dumps(metrics, indent=2))

    elif args.command == "sweep":
        results = run_parameter_sweep(
            csv_path=args.csv,
            output_dir=args.output_dir,
            results_dir=args.results_dir,
            checkpoint_dir=args.checkpoint_dir,
            force_fresh=args.force_fresh,
        )

        print(f"\n✅ Sweep complete! Best model:")
        print(f"   {results[0]['combo']}")
        print(f"   Return: {results[0]['total_return']:.2f}%")


if __name__ == "__main__":
    main()
