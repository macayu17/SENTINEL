# 🚀 RL Training System - Complete Setup Guide

Your Sentinel RL training system is now ready with full checkpoint management and automated workflows.

## ⚡ 30-Second Quick Start

```bash
cd /Users/anindhithsankanna/CS\ Projects/Sentinel

# Train
./rl_train.sh train my_model ppo 250000

# Backtest
./rl_train.sh backtest my_model

# Hyperparameter sweep
./rl_train.sh sweep
```

## 📂 What Was Created

### 1. **Main Training Script**
- `backend/scripts/train_backtest_rl_system.py` — Full training/backtest/checkpoint system
  - 📊 Supports PPO and DQN algorithms
  - 💾 Automatic model checkpointing
  - 🔄 Resumable parameter sweeps
  - 📈 Detailed backtest metrics

### 2. **Convenience Wrapper (Bash)**
- `./rl_train.sh` — Easy command-line interface
  - `train` — Train models with sensible defaults
  - `backtest` — Test trained models
  - `sweep` — Hyperparameter search (resumable)
  - `list` — Show available models
  - `tensorboard` — Monitor training
  - `cleanup` — Clean up files

### 3. **Documentation**
- `RL_TRAINING_GUIDE.md` — Comprehensive reference
- `RL_QUICK_START.md` — Cheat sheet for quick commands
- `backend/RL_CONFIG_TEMPLATES.py` — Configuration examples

## 🎯 Your Complete Workflow

### Step 1: Prepare Data
```bash
# Upload your historical OHLCV data
cp /path/to/historical_data.csv backend/data/historical_1m.csv

# Verify
ls -lh backend/data/historical_1m.csv
```

**CSV Format (required):**
```
timestamp,open,high,low,close,volume
2024-01-15 09:15:00,500.0,510.0,495.0,505.0,100000
2024-01-15 09:16:00,505.0,515.0,502.0,512.0,120000
...
```

### Step 2: Quick Test
```bash
./rl_train.sh train test_model ppo 50000

# Should complete in ~5 minutes
# Output: Model saved to models/rl_training/test_model_ppo
```

### Step 3: Backtest
```bash
./rl_train.sh backtest test_model

# Output shows metrics like:
# - Total return: 5.23%
# - Win rate: 62%
# - Sharpe: 1.34
# - Max drawdown: -7.2%
```

### Step 4: Hyperparameter Search
```bash
./rl_train.sh sweep

# Sweeps automatically:
# - Learning rates: 1e-4, 3e-4, 1e-3
# - Architectures: (128,128), (256,256), (512,512)
# - Algorithms: PPO
# 
# Safe to interrupt (Ctrl+C) and resume later!
```

### Step 5: Full Production Training
```bash
# Based on sweep results, use best params
./rl_train.sh train production_model ppo 500000 3e-4 256,256

# Monitor with tensorboard
./rl_train.sh tensorboard  # Open http://localhost:6006
```

### Step 6: Multi-Timeframe Testing
```bash
./rl_train.sh backtest production_model ppo 1min
./rl_train.sh backtest production_model ppo 5min
./rl_train.sh backtest production_model ppo 15min

# Model trained at 1min, tested at different execution frequencies
```

## 🗂️ Directory Structure

```
Sentinel/
├── backend/data/                               # 📤 Upload data here
│   └── historical_1m.csv
│
├── backend/models/rl_training/
│   ├── test_model_ppo                          # Trained models
│   ├── production_model_ppo
│   └── balanced_model_ppo
│
├── backend/checkpoints/
│   ├── rl_training/
│   │   ├── checkpoint_metadata.json            # All models + metrics
│   │   └── best_models.json                    # Best model pointers
│   └── rl_sweep/
│       └── sweep_checkpoint.json               # Progress (resumable!)
│
├── backend/results/
│   ├── rl_training/
│   │   └── backtest_results_*.json
│   └── rl_sweep/
│       └── sweep_results_*.json
│
├── backend/tensorboard_logs/
│   ├── intraday_ppo/                           # Training curves
│   └── intraday_dqn/
│
├── backend/scripts/
│   └── train_backtest_rl_system.py             # Main script
│
├── RL_TRAINING_GUIDE.md                        # Full reference
├── RL_QUICK_START.md                           # Cheat sheet
└── rl_train.sh                                 # Wrapper script
```

## 🛠️ Commands Reference

### Training
```bash
# Default (PPO, 250k steps)
./rl_train.sh train

# Named model
./rl_train.sh train my_model

# Full control
./rl_train.sh train my_model ppo 250000 3e-4 256,256

# DQN algorithm
./rl_train.sh train my_model dqn 250000
```

### Backtesting
```bash
# Default (5min bars)
./rl_train.sh backtest my_model

# Specific timeframe
./rl_train.sh backtest my_model ppo 1min
./rl_train.sh backtest my_model ppo 15min
```

### Sweeps (Resumable!)
```bash
# Start sweep
./rl_train.sh sweep
# [Ctrl+C after 30 minutes]

# Resume automatically
./rl_train.sh sweep
# Continues from checkpoint

# Force restart
./rl_train.sh sweep --force-fresh
```

### Monitoring
```bash
./rl_train.sh list               # Show models & results
./rl_train.sh tensorboard        # Start tensorboard
./rl_train.sh tensorboard 8888   # Custom port
```

## 📊 Understanding Backtest Output

```json
{
  "avg_return": 0.45,           // Average session return (%)
  "total_return": 12.34,        // Sum of all returns (%)
  "win_rate": 62.5,             // Profitable sessions (%)
  "sharpe": 1.23,               // Risk-adjusted return
  "max_drawdown": -8.5,         // Peak-to-trough decline (%)
  "profit_factor": 1.45,        // Gross profit / Gross loss
  "num_trades": 24              // Total trades
}
```

**Good thresholds:**
- Win rate > 55%
- Sharpe > 1.0
- Max drawdown < -10%
- Profit factor > 1.2

## 💾 Checkpoint System (Key Feature!)

### Auto-Resume Mid-Sweep
```bash
# Running sweep...
./rl_train.sh sweep
# [After 1 hour, machine crashes]

# Just re-run:
./rl_train.sh sweep
# ✅ Automatically resumes from saved checkpoint!
```

### View Checkpoints
```bash
# See all models
./rl_train.sh list

# Or manually inspect
cat backend/checkpoints/rl_training/checkpoint_metadata.json | python3 -m json.tool

# Load in Python
import json
with open("backend/checkpoints/rl_training/best_models.json") as f:
    best = json.load(f)
    for name, info in best.items():
        print(f"{name}: {info['metrics']}")
```

## 🎓 Example: Complete 2-Day Workflow

**Day 1 (Initial Testing)**
```bash
# 1. Quick test
./rl_train.sh train quick ppo 50000
./rl_train.sh backtest quick  # 5 min
# Result: 2% return, 55% win rate → OK, continue

# 2. Hyperparameter search (2-3 hours)
./rl_train.sh sweep
# Best found: lr=3e-4, arch=256,256 with 8.5% return

# 3. Preliminary full training
./rl_train.sh train v1 ppo 250000 3e-4 256,256
./rl_train.sh backtest v1  # 5 min
# Result: 8.3% return, 62% win rate → good!
```

**Day 2 (Production Training)**
```bash
# 1. Extended training (2-3 hours)
./rl_train.sh train production ppo 500000 3e-4 256,256

# 2. Multi-timeframe testing (30 min)
./rl_train.sh backtest production ppo 1min
./rl_train.sh backtest production ppo 5min    # ← Deploy at 5min
./rl_train.sh backtest production ppo 15min

# 3. Final analysis
./rl_train.sh tensorboard  # 📊 Monitor curves
./rl_train.sh list         # 📋 View all results
```

## ⚙️ Hyperparameter Tuning Guide

### Learning Rate (`--lr`)
```
1e-4 (very slow):   Stable, takes longer
3e-4 (balanced):    Recommended starting point
1e-3 (fast):        May be unstable, use with caution
```

### Network Architecture (`--net-arch`)
```
128,128 (small):    Fast training, less capacity
256,256 (medium):   Balanced, recommended
512,512 (large):    Slower, more capacity
```

### Training Steps (`--timesteps`)
```
50,000:     Quick testing
250,000:    Good baseline
500,000:    Thorough training
1,000,000:  Very deep learning
```

### To Improve Performance
1. **More training:** 250k → 500k timesteps
2. **Better params:** Run `./rl_train.sh sweep` to find optimal
3. **Larger network:** 256,256 → 512,512
4. **More data:** Longer historical period

### To Reduce Risk (Drawdown)
1. Use smaller position sizes
2. Increase trailing stop percentage
3. Use `--lr 1e-4` (slower learning)
4. Use larger network (more stable)

## 🔍 Troubleshooting

| Issue | Solution |
|-------|----------|
| "No historical_1m.csv" | Upload data: `cp data.csv backend/data/historical_1m.csv` |
| Poor performance | Run sweep: `./rl_train.sh sweep` |
| Memory error | Use smaller model: `--net-arch 128,128` |
| Sweep interrupted | Just re-run: `./rl_train.sh sweep` (auto-resumes!) |
| Negative returns | Try different hyperparameters or more training |

## 📈 Monitoring Training

```bash
# Start tensorboard
./rl_train.sh tensorboard

# Open browser to http://localhost:6006
# Watch curves update in real-time:
# - Episode reward
# - Policy loss
# - Value function loss
```

## 🎁 Advanced: Direct Python Usage

```bash
# Train with full control
python backend/scripts/train_backtest_rl_system.py train \
  --csv backend/data/historical_1m.csv \
  --name model_v2 \
  --algo ppo \
  --timesteps 300000 \
  --lr 2e-4 \
  --net-arch 384,384

# Backtest
python backend/scripts/train_backtest_rl_system.py backtest \
  --csv backend/data/historical_1m.csv \
  --model backend/models/rl_training/model_v2_ppo \
  --timeframe 5min

# Sweep
python backend/scripts/train_backtest_rl_system.py sweep \
  --csv backend/data/historical_1m.csv \
  --force-fresh
```

## 📚 Additional Resources

1. **Quick Reference:** `RL_QUICK_START.md`
2. **Full Manual:** `RL_TRAINING_GUIDE.md`
3. **Config Templates:** `backend/RL_CONFIG_TEMPLATES.py`
4. **Main Script:** `backend/scripts/train_backtest_rl_system.py`

## 🚀 Next Steps

1. ✅ Prepare data → `backend/data/historical_1m.csv`
2. ⚡ Quick test → `./rl_train.sh train test ppo 50000`
3. 📊 Backtest → `./rl_train.sh backtest test`
4. 🔄 Full sweep → `./rl_train.sh sweep`
5. 🎯 Production training → `./rl_train.sh train final ppo 500000 3e-4 256,256`

---

## 💡 Pro Tips

- **Resume friendly:** All sweeps save checkpoints automatically
- **Multi-timeframe:** Train at 1min, deploy at 5min or 15min
- **Monitor live:** Use tensorboard to watch training progress
- **Compare models:** `./rl_train.sh list` shows all metrics
- **Checkpoint backups:** Keep `backend/checkpoints/` for history

## 📞 Need Help?

```bash
./rl_train.sh help              # Full command reference
cat RL_QUICK_START.md           # Quick cheat sheet
cat RL_TRAINING_GUIDE.md        # Comprehensive guide
```

---

**You're all set!** 🎉 Start with:

```bash
./rl_train.sh train my_model ppo 50000
./rl_train.sh backtest my_model
```

Happy training! 🚀📈
