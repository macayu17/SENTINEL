#!/usr/bin/env python3
"""
Configuration templates for RL training/backtesting workflows.
Copy and modify these for your specific use cases.
"""

# ============================================================
#                   EXAMPLE CONFIGURATIONS
# ============================================================

# ── Environment Configuration ────────────────────────────────
DEFAULT_ENV_CONFIG = {
    "lookback": 30,  # Number of historical candles to observe
    "initial_cash": 1_000_000,  # Starting capital
    "lot_size": 50,  # Share lot size
    "transaction_cost_bps": 10.0,  # 0.1% commission
    "trailing_stop_pct": 0.005,  # 0.5% stop loss
    "morning_minutes": 60,  # Trading window (first 60 minutes)
    "random_reset": True,  # Randomize reset for training
}

# ── Training Configurations ──────────────────────────────────

# Quick test: verify everything works
QUICK_TEST_CONFIG = {
    "algorithm": "ppo",
    "timesteps": 50_000,
    "learning_rate": 3e-4,
    "batch_size": 256,
    "net_arch": (256, 256),
    "n_steps": 1024,
    "tensorboard_log": "./tensorboard_logs/quick_test",
}

# Balanced: good for most use cases
BALANCED_CONFIG = {
    "algorithm": "ppo",
    "timesteps": 250_000,
    "learning_rate": 3e-4,
    "batch_size": 256,
    "net_arch": (256, 256),
    "n_steps": 1024,
    "gamma": 0.995,  # Discount factor
    "gae_lambda": 0.97,  # GAE parameter
    "clip_range": 0.2,  # PPO clipping range
    "ent_coef": 0.005,  # Entropy coefficient
    "tensorboard_log": "./tensorboard_logs/balanced",
}

# Deep training: thorough exploration
DEEP_TRAINING_CONFIG = {
    "algorithm": "ppo",
    "timesteps": 500_000,
    "learning_rate": 1e-4,  # Slower learning
    "batch_size": 256,
    "net_arch": (512, 512),  # Larger network
    "n_steps": 2048,  # More steps per update
    "gamma": 0.9995,  # Stronger reward discounting
    "gae_lambda": 0.99,  # Better GAE estimation
    "clip_range": 0.1,  # Tighter clipping
    "ent_coef": 0.001,  # Less exploration
    "tensorboard_log": "./tensorboard_logs/deep",
}

# Conservative: minimize drawdown
CONSERVATIVE_CONFIG = {
    "algorithm": "ppo",
    "timesteps": 300_000,
    "learning_rate": 1e-4,  # Very slow learning
    "batch_size": 512,  # Larger batches = more stable
    "net_arch": (256, 256),
    "n_steps": 2048,
    "gamma": 0.99,  # Shorter horizon
    "gae_lambda": 0.95,
    "clip_range": 0.1,  # Very conservative
    "ent_coef": 0.01,  # More exploration
    "tensorboard_log": "./tensorboard_logs/conservative",
}

# Aggressive: maximize returns (higher risk)
AGGRESSIVE_CONFIG = {
    "algorithm": "ppo",
    "timesteps": 200_000,
    "learning_rate": 1e-3,  # Fast learning
    "batch_size": 128,  # Small batches = higher variance
    "net_arch": (512, 512),  # Large network
    "n_steps": 512,  # Fewer steps per update
    "gamma": 0.999,  # Long horizon
    "gae_lambda": 0.98,
    "clip_range": 0.3,  # Loose clipping
    "ent_coef": 0.001,  # Less exploration
    "tensorboard_log": "./tensorboard_logs/aggressive",
}

# DQN baseline: compare against PPO
DQN_CONFIG = {
    "algorithm": "dqn",
    "timesteps": 250_000,
    "learning_rate": 1e-4,
    "buffer_size": 100_000,
    "batch_size": 256,
    "gamma": 0.995,
    "exploration_fraction": 0.15,  # 15% exploration
    "exploration_final_eps": 0.05,  # Final exploration rate
    "target_update_interval": 2000,
    "net_arch": (256, 256),
    "tensorboard_log": "./tensorboard_logs/dqn",
}

# ── Backtest Configurations ──────────────────────────────────

BACKTEST_TIMEFRAMES = {
    "1min": "Train at 1m, test at 1m (highest frequency)",
    "5min": "Train at 1m, deploy at 5m (standard)",
    "15min": "Train at 1m, deploy at 15m (smoother execution)",
}

# ── Sweep Configurations ──────────────────────────────────────

SWEEP_LEARNING_RATES = [
    1e-4,  # Very slow
    3e-4,  # Slow
    1e-3,  # Fast
    3e-3,  # Very fast
]

SWEEP_ARCHITECTURES = [
    (128, 128),  # Small
    (256, 256),  # Medium (recommended)
    (512, 512),  # Large
    (1024, 512),  # Very large
]

SWEEP_BATCH_SIZES = [
    128,  # Small
    256,  # Medium
    512,  # Large
]

# ============================================================
#                   USAGE EXAMPLES
# ============================================================

"""
Using these configurations:

# 1. Quick test
python backend/scripts/train_backtest_rl_system.py train \
  --csv backend/data/historical_1m.csv \
  --name quick_test \
  --algo ppo \
  --timesteps 50000 \
  --lr 3e-4 \
  --net-arch 256,256

# 2. Balanced training (recommended)
python backend/scripts/train_backtest_rl_system.py train \
  --csv backend/data/historical_1m.csv \
  --name balanced_model \
  --algo ppo \
  --timesteps 250000 \
  --lr 3e-4 \
  --net-arch 256,256

# 3. Deep training (2+ hours)
python backend/scripts/train_backtest_rl_system.py train \
  --csv backend/data/historical_1m.csv \
  --name deep_model \
  --algo ppo \
  --timesteps 500000 \
  --lr 1e-4 \
  --net-arch 512,512

# 4. Conservative (minimize risk)
python backend/scripts/train_backtest_rl_system.py train \
  --csv backend/data/historical_1m.csv \
  --name conservative_model \
  --algo ppo \
  --timesteps 300000 \
  --lr 1e-4 \
  --net-arch 256,256

# 5. Aggressive (maximize returns)
python backend/scripts/train_backtest_rl_system.py train \
  --csv backend/data/historical_1m.csv \
  --name aggressive_model \
  --algo ppo \
  --timesteps 200000 \
  --lr 1e-3 \
  --net-arch 512,512

# 6. DQN comparison
python backend/scripts/train_backtest_rl_system.py train \
  --csv backend/data/historical_1m.csv \
  --name dqn_baseline \
  --algo dqn \
  --timesteps 250000 \
  --lr 1e-4 \
  --net-arch 256,256

# 7. Backtest at different timeframes
python backend/scripts/train_backtest_rl_system.py backtest \
  --csv backend/data/historical_1m.csv \
  --model models/rl_training/balanced_model_ppo \
  --timeframe 1min

python backend/scripts/train_backtest_rl_system.py backtest \
  --csv backend/data/historical_1m.csv \
  --model models/rl_training/balanced_model_ppo \
  --timeframe 5min

python backend/scripts/train_backtest_rl_system.py backtest \
  --csv backend/data/historical_1m.csv \
  --model models/rl_training/balanced_model_ppo \
  --timeframe 15min

# 8. Full hyperparameter sweep
python backend/scripts/train_backtest_rl_system.py sweep \
  --csv backend/data/historical_1m.csv

# 9. Resume interrupted sweep
python backend/scripts/train_backtest_rl_system.py sweep \
  --csv backend/data/historical_1m.csv

# 10. Start fresh sweep
python backend/scripts/train_backtest_rl_system.py sweep \
  --csv backend/data/historical_1m.csv \
  --force-fresh
"""

# ============================================================
#              PERFORMANCE EXPECTATIONS
# ============================================================

"""
Expected performance ranges (intraday trading):

Good model (above these thresholds):
  - Total return:      > 5%
  - Win rate:          > 55%
  - Sharpe ratio:      > 1.0
  - Max drawdown:      < -10%
  - Profit factor:     > 1.2

Excellent model (highly profitable):
  - Total return:      > 15%
  - Win rate:          > 65%
  - Sharpe ratio:      > 1.5
  - Max drawdown:      < -5%
  - Profit factor:     > 2.0

Poor model (investigate):
  - Total return:      < 0% (losing money)
  - Win rate:          < 50% (worse than random)
  - Sharpe ratio:      < 0.5 (very risky)
  - Max drawdown:      > -20% (too volatile)
  - Profit factor:     < 1.0 (more loss than profit)
"""

# ============================================================
#              QUICK REFERENCE: PARAMETER TUNING
# ============================================================

"""
To improve performance, try:

1. Increase training steps:
   250k → 500k → 1M (more learning)

2. Lower learning rate:
   3e-4 → 1e-4 (more stable)

3. Larger network:
   256,256 → 512,512 (more capacity)

4. More augmentation:
   --augment-copies 1 → 3 (more diversity)

To reduce overfitting:

1. Lower learning rate (slower learning)
2. Higher entropy coefficient (more exploration)
3. Smaller network (less capacity)
4. More data augmentation
5. Dropout (if available)

To reduce drawdown:

1. Use CONSERVATIVE_CONFIG
2. Increase trailing stop percentage
3. Increase transaction cost (realistic commission)
4. Use smaller position sizes

To improve Sharpe ratio:

1. Optimize for consistency (smaller variance)
2. Use PPO (more stable than DQN)
3. Increase GAE lambda (0.97 → 0.99)
4. Decrease learning rate
"""

# ============================================================
#            CHECKPOINT & MODEL MANAGEMENT
# ============================================================

"""
Checkpoint locations:

backend/
├── models/
│   ├── rl_training/
│   │   └── [model_name]_[algo]         ← Trained models
│   └── rl_sweep/
│       └── [combo_name]                 ← Sweep results
│
├── checkpoints/
│   ├── rl_training/
│   │   ├── checkpoint_metadata.json     ← All models metadata
│   │   └── best_models.json             ← Best models pointer
│   └── rl_sweep/
│       └── sweep_checkpoint.json        ← Sweep progress (resumable)
│
└── results/
    ├── rl_training/
    │   └── backtest_results_*.json      ← Backtest metrics
    └── rl_sweep/
        └── sweep_results_*.json         ← Ranked parameters

Loading best model in code:

import json

# Load checkpoint metadata
with open("backend/checkpoints/rl_training/checkpoint_metadata.json") as f:
    metadata = json.load(f)

# List all models
for name, checkpoint in metadata["checkpoints"].items():
    print(f"{name}: {checkpoint['metrics']}")

# Find best by return
best = max(
    metadata["checkpoints"].values(),
    key=lambda x: x["metrics"].get("total_return", 0)
)
print(f"Best model path: {best['model_path']}")
print(f"Best metrics: {best['metrics']}")
"""

if __name__ == "__main__":
    # Print available configurations
    print("Available Training Configurations:")
    print("  - QUICK_TEST_CONFIG")
    print("  - BALANCED_CONFIG")
    print("  - DEEP_TRAINING_CONFIG")
    print("  - CONSERVATIVE_CONFIG")
    print("  - AGGRESSIVE_CONFIG")
    print("  - DQN_CONFIG")
    print()
    print("Use these as templates for your training runs.")
    print()
    print("Example:")
    print("  python backend/scripts/train_backtest_rl_system.py train \\")
    print("    --csv backend/data/historical_1m.csv \\")
    print("    --name my_model \\")
    print("    --timesteps 250000 \\")
    print("    --lr 3e-4 \\")
    print("    --net-arch 256,256")
