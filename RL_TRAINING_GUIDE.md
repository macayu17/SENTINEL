# RL Training + Backtesting + Checkpoint System

Comprehensive system for training, backtesting, and managing reinforcement learning models with checkpoint recovery.

## Features

✅ **Model Checkpointing**
- Automatic model saving after each training run
- Best model tracking by performance metrics
- Metadata storage (config, metrics, timestamp)

✅ **Training with Resume**
- Resume interrupted training runs
- Tracks training progress in checkpoints
- Supports both PPO and DQN algorithms

✅ **Parameter Sweeps**
- Sweep learning rates, network architectures, algorithms
- Progress checkpointing — safe to Ctrl+C and resume
- Automatic ranking and metrics comparison

✅ **Detailed Backtesting**
- Session-by-session performance tracking
- Metrics: Sharpe ratio, max drawdown, win rate, profit factor
- Comparison tables across configurations

✅ **Comprehensive Logging**
- Results saved to JSON and CSV
- Tensorboard integration
- Timestamped log files

## Quick Start

### 1. Single Training Run

```bash
python backend/scripts/train_backtest_rl_system.py train \
  --csv data/historical_1m.csv \
  --name my_first_model \
  --algo ppo \
  --timesteps 250000 \
  --lr 3e-4 \
  --net-arch 256,256
```

**Output:**
- `models/rl_training/my_first_model_ppo` — trained model
- `checkpoints/rl_training/checkpoint_metadata.json` — metadata
- `checkpoints/rl_training/best_models.json` — best models info

### 2. Backtest Trained Model

```bash
python backend/scripts/train_backtest_rl_system.py backtest \
  --csv data/historical_1m.csv \
  --model models/rl_training/my_first_model_ppo \
  --algo ppo \
  --timeframe 5min
```

**Output:**
```
Backtest Summary:
{
  "avg_return": 0.45,
  "total_return": 12.34,
  "win_rate": 62.5,
  "sharpe": 1.23,
  "max_drawdown": -8.5,
  "profit_factor": 1.45,
  "num_trades": 24
}
```

### 3. Hyperparameter Sweep

```bash
python backend/scripts/train_backtest_rl_system.py sweep \
  --csv data/historical_1m.csv \
  --output-dir models/rl_sweep \
  --results-dir results/rl_sweep
```

**Features:**
- Sweeps learning rates: [1e-4, 3e-4, 1e-3]
- Sweeps architectures: [(128,128), (256,256), (512,512)]
- Auto-resumes if interrupted (Ctrl+C)
- Clear with `--force-fresh` flag

**Output Example:**
```
SWEEP RESULTS — RANKED BY TOTAL RETURN
Rank  Algorithm  Learning Rate   Net Arch        Return %     Win %     Sharpe    Max DD %
───────────────────────────────────────────────────────────────────────────────────────
1     ppo        3.000000e-04    (256, 256)      15.23        65.0      1.45      -5.2
2     ppo        1.000000e-04    (256, 256)      12.45        62.0      1.23      -6.1
3     ppo        1.000000e-03    (512, 512)       8.90        58.0      0.95      -9.3
─────────────────────────────────────────────────────────────────────────────────────────

✅ Results saved → results/rl_sweep/sweep_results_20260428_143022.json
```

## Directory Structure

```
backend/
  data/                          # 📁 Upload historical data here
    historical_1m.csv            # OHLCV data
  
  models/                        # 📁 Trained models
    rl_training/
      my_first_model_ppo         # Trained PPO model
      model2_dqn                 # Trained DQN model
    rl_sweep/
      ppo_lr1e-4_arch128_128     # Sweep results
  
  checkpoints/                   # 📁 Training checkpoints
    rl_training/
      checkpoint_metadata.json   # Model metadata & metrics
      best_models.json           # Best model pointers
    rl_sweep/
      sweep_checkpoint.json      # Sweep progress (auto-resumable)
  
  results/                       # 📁 Backtest results
    rl_training/
    rl_sweep/
      sweep_results_20260428.json
  
  tensorboard_logs/              # 📁 Training curves
    intraday_ppo/
    intraday_dqn/
```

## Checkpoint System

### Resume Training After Interruption

If a sweep is interrupted:
```bash
# Auto-resumes from checkpoint_metadata.json
python backend/scripts/train_backtest_rl_system.py sweep \
  --csv data/historical_1m.csv
```

### Restart Fresh

```bash
# Clear old checkpoint, start fresh
python backend/scripts/train_backtest_rl_system.py sweep \
  --csv data/historical_1m.csv \
  --force-fresh
```

### Inspect Checkpoints

```python
import json

# See all saved models and metrics
with open("checkpoints/rl_training/checkpoint_metadata.json") as f:
    metadata = json.load(f)
    for name, cp in metadata["checkpoints"].items():
        print(f"{name}: Return={cp['metrics']['total_return']:.2f}%")

# Get best model by metric
with open("checkpoints/rl_training/best_models.json") as f:
    best = json.load(f)
    for model_name, info in best.items():
        print(f"Best {model_name}: {info}")
```

## Configuration

### Environment Config
```python
IntradayEnvConfig:
  lookback: int = 30                      # Candles to look back
  initial_cash: float = 1_000_000         # Starting capital
  lot_size: int = 50                      # Share lot size
  transaction_cost_bps: float = 10.0      # 0.1% commission
  trailing_stop_pct: float = 0.005        # 0.5% stop loss
  morning_minutes: int = 60               # Trade window
```

### PPO Config
```python
PPOTrainingConfig:
  total_timesteps: int = 250_000
  learning_rate: float = 3e-4
  n_steps: int = 1024
  batch_size: int = 256
  gamma: float = 0.995                    # Discount factor
  gae_lambda: float = 0.97                # GAE parameter
```

## Metrics Explained

| Metric | Meaning |
|--------|---------|
| **total_return** | Sum of all daily returns (%) |
| **win_rate** | % of profitable sessions |
| **sharpe** | Risk-adjusted return (higher = better) |
| **max_drawdown** | Largest peak-to-trough decline (%) |
| **profit_factor** | Gross profit / Gross loss |
| **num_trades** | Total trades executed |

## Best Practices

### 1. Data Preparation
```bash
# Ensure your CSV has columns:
# timestamp, open, high, low, close, volume
# Format: YYYY-MM-DD HH:MM:SS
```

### 2. Training Progression
```bash
# Start with shorter runs to debug
--timesteps 50000 --lr 1e-3

# Then full training
--timesteps 250000 --lr 3e-4
```

### 3. Evaluate Multiple Timeframes
```bash
# Train at 1m, test at different frames
python train_backtest_rl_system.py backtest --timeframe 1min
python train_backtest_rl_system.py backtest --timeframe 5min
python train_backtest_rl_system.py backtest --timeframe 15min
```

### 4. Use Sweeps for Hyperparameter Tuning
```bash
# Run sweep to find best learning rate
python train_backtest_rl_system.py sweep --csv data/historical_1m.csv

# Take top result and train longer
python train_backtest_rl_system.py train \
  --csv data/historical_1m.csv \
  --lr 3e-4 \
  --timesteps 500000
```

## Troubleshooting

### Model Not Saved
- Check `models/rl_training/` directory exists
- Verify write permissions: `chmod 755 models/`

### Sweep Interrupted
- Just re-run the command (auto-resumes)
- To restart: add `--force-fresh` flag

### Poor Performance
- Increase `--timesteps` (more training)
- Try different `--lr` values
- Use `sweep` to find optimal hyperparameters

### Out of Memory
- Reduce batch_size in config
- Use fewer augmentation copies: `--augment-copies 1`
- Reduce `--timesteps` for faster iteration

## Example Workflow

```bash
#!/bin/bash

# 1. Prepare data (upload to backend/data/)
cp /path/to/historical_data.csv backend/data/historical_1m.csv

# 2. Quick test run
python backend/scripts/train_backtest_rl_system.py train \
  --csv backend/data/historical_1m.csv \
  --name test_model \
  --timesteps 50000

# 3. Backtest
python backend/scripts/train_backtest_rl_system.py backtest \
  --csv backend/data/historical_1m.csv \
  --model models/rl_training/test_model_ppo

# 4. Hyperparameter sweep
python backend/scripts/train_backtest_rl_system.py sweep \
  --csv backend/data/historical_1m.csv

# 5. Full training with best params
python backend/scripts/train_backtest_rl_system.py train \
  --csv backend/data/historical_1m.csv \
  --name final_model \
  --lr 3e-4 \
  --timesteps 500000

# 6. Final backtest
python backend/scripts/train_backtest_rl_system.py backtest \
  --csv backend/data/historical_1m.csv \
  --model models/rl_training/final_model_ppo \
  --timeframe 5min
```

## Tensorboard Monitoring

```bash
# Watch training curves in real-time
tensorboard --logdir=backend/tensorboard_logs/

# View in browser: http://localhost:6006
```

## Command Reference

### Train
```bash
python backend/scripts/train_backtest_rl_system.py train [OPTIONS]

Options:
  --csv CSV_PATH              ✓ REQUIRED: Path to OHLCV CSV
  --name NAME                 Model name (default: ppo_intraday)
  --algo {ppo,dqn}           Algorithm (default: ppo)
  --timesteps N              Training steps (default: 250000)
  --lr FLOAT                 Learning rate (default: 3e-4)
  --net-arch "128,256"       Network layers (default: 256,256)
  --no-augment               Disable data augmentation
  --augment-copies N         Augmentation copies (default: 1)
```

### Backtest
```bash
python backend/scripts/train_backtest_rl_system.py backtest [OPTIONS]

Options:
  --csv CSV_PATH               ✓ REQUIRED: Path to OHLCV CSV
  --model MODEL_PATH          ✓ REQUIRED: Path to saved model
  --algo {ppo,dqn}           Algorithm (default: ppo)
  --timeframe {1min,5min,15min} (default: 5min)
```

### Sweep
```bash
python backend/scripts/train_backtest_rl_system.py sweep [OPTIONS]

Options:
  --csv CSV_PATH               ✓ REQUIRED: Path to OHLCV CSV
  --force-fresh               Clear old results, restart
```

## Support

For issues or questions, check:
1. Checkpoint status: `cat checkpoints/rl_training/checkpoint_metadata.json`
2. Tensorboard logs: `tensorboard --logdir=tensorboard_logs/`
3. Recent results: `ls -la results/rl_training/`
