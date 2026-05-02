# RL Training Quick Reference

## 🚀 Quickest Start (3 minutes)

```bash
cd /Users/anindhithsankanna/CS\ Projects/Sentinel

# 1️⃣  Train
./rl_train.sh train test_model ppo 50000

# 2️⃣  Backtest
./rl_train.sh backtest test_model

# Done! ✅
```

## 📊 Full Workflow (30 minutes)

```bash
# 1. Check available models
./rl_train.sh list

# 2. Run hyperparameter sweep (auto-resumes if interrupted)
./rl_train.sh sweep
# Output: Best config, sorted by return

# 3. Train with best params found from sweep
./rl_train.sh train final_model ppo 250000 3e-4 256,256

# 4. Backtest at multiple timeframes
./rl_train.sh backtest final_model ppo 1min
./rl_train.sh backtest final_model ppo 5min
./rl_train.sh backtest final_model ppo 15min

# 5. Monitor with tensorboard (in new terminal)
./rl_train.sh tensorboard
# Open: http://localhost:6006
```

## 🎯 Training Commands Cheat Sheet

### Train Models
```bash
./rl_train.sh train                            # Default: PPO, 250k steps
./rl_train.sh train my_model ppo 250000        # Explicit PPO
./rl_train.sh train dqn_model dqn 250000       # DQN algorithm
./rl_train.sh train fast ppo 50000 1e-3        # Fast test run
./rl_train.sh train slow ppo 500000 1e-5       # Slow, thorough training
```

### Backtest Models  
```bash
./rl_train.sh backtest my_model                # Default: 5min bars
./rl_train.sh backtest my_model ppo 1min       # 1-minute bars
./rl_train.sh backtest my_model ppo 15min      # 15-minute bars
./rl_train.sh backtest dqn_model dqn 5min      # DQN model
```

### Parameter Sweep
```bash
./rl_train.sh sweep                 # Resume from last checkpoint
./rl_train.sh sweep --force-fresh   # Start over, clear old results
```

### List & Monitor
```bash
./rl_train.sh list                  # Show all models and results
./rl_train.sh tensorboard           # Monitor training curves
./rl_train.sh tensorboard 8888      # Custom port
./rl_train.sh cleanup               # Clean up old training files
```

## 📁 Where Files Are Saved

```
Sentinel/
├── backend/
│   ├── data/
│   │   └── historical_1m.csv          ← Upload data here
│   ├── models/rl_training/
│   │   ├── ppo_intraday_ppo          ← Trained models
│   │   ├── my_model_ppo
│   │   └── final_model_ppo
│   ├── checkpoints/rl_training/
│   │   ├── checkpoint_metadata.json   ← Model metadata
│   │   └── best_models.json           ← Best model pointers
│   ├── results/rl_training/
│   │   └── backtest_results_*.json    ← Backtest metrics
│   └── tensorboard_logs/
│       └── intraday_ppo/              ← Training curves
├── results/rl_sweep/                  ← Sweep results
│   └── sweep_results_*.json           ← Ranked parameters
└── checkpoints/rl_sweep/
    └── sweep_checkpoint.json          ← Sweep progress (resumable)
```

## 💾 Checkpoint System

### Auto-Resume After Interruption
```bash
# Running sweep...
./rl_train.sh sweep
# [Interrupt with Ctrl+C after 30 minutes]

# Just re-run — it resumes!
./rl_train.sh sweep
# Continues from where it left off
```

### Clear Old Results
```bash
# Start fresh sweep
./rl_train.sh sweep --force-fresh

# Or manually
rm -f backend/checkpoints/rl_sweep/sweep_checkpoint.json
```

## 📈 Understanding Backtest Output

```
Backtest Summary:
{
  "avg_return": 0.45,           # Average per-session return (%)
  "total_return": 12.34,        # Sum of all returns (%)
  "win_rate": 62.5,             # % profitable sessions
  "sharpe": 1.23,               # Risk-adjusted return (higher = better)
  "max_drawdown": -8.5,         # Largest peak-to-trough decline (%)
  "profit_factor": 1.45,        # Gross profit / Gross loss
  "num_trades": 24              # Total trades executed
}
```

**Good values:**
- Win rate > 55%
- Sharpe > 1.0
- Max drawdown < -10%
- Profit factor > 1.2

## 🔧 Tuning Hyperparameters

### Learning Rate (--lr)
```bash
1e-4    # Slow, stable learning
3e-4    # Balanced (recommended)
1e-3    # Fast, may be unstable
```

### Network Architecture (--net-arch)
```bash
128,128      # Small, fast training
256,256      # Balanced (recommended)
512,512      # Large, slower training
```

### Training Steps (--timesteps)
```bash
50000       # Quick test
250000      # Good baseline
500000      # Thorough training
1000000     # Very deep training
```

## ⚠️ Common Issues

### "No historical_1m.csv found"
```bash
# Solution: Upload data
cp /path/to/your/data.csv backend/data/historical_1m.csv
```

### Sweep keeps restarting?
```bash
# Clear checkpoint and retry
./rl_train.sh sweep --force-fresh
```

### Poor performance (negative returns)
```bash
# Try different hyperparameters
./rl_train.sh train test2 ppo 100000 1e-4 256,256
./rl_train.sh backtest test2

# Or run full sweep
./rl_train.sh sweep
```

### Out of memory
```bash
# Reduce training steps
./rl_train.sh train small_model ppo 50000

# Use smaller network
./rl_train.sh train small_model ppo 250000 3e-4 128,128
```

## 🎓 Example Workflow: Complete Training

```bash
# Day 1: Initial exploration
./rl_train.sh train quick ppo 50000      # Test run
./rl_train.sh backtest quick             # Check performance

# Day 2: Hyperparameter search
./rl_train.sh sweep                      # 2-3 hours
./rl_train.sh list                       # See top results
# Found: lr=3e-4, arch=256,256 is best

# Day 3: Production training
./rl_train.sh train production ppo 500000 3e-4 256,256
# This will take 1-2 hours

# Day 4: Thorough backtesting
./rl_train.sh backtest production ppo 1min
./rl_train.sh backtest production ppo 5min
./rl_train.sh backtest production ppo 15min

# Day 5: Monitor & iterate
./rl_train.sh tensorboard
# Check curves in http://localhost:6006
```

## 📚 Direct Python Usage

If you prefer Python directly:

```bash
# Train
python backend/scripts/train_backtest_rl_system.py train \
  --csv backend/data/historical_1m.csv \
  --name my_model \
  --algo ppo \
  --timesteps 250000

# Backtest
python backend/scripts/train_backtest_rl_system.py backtest \
  --csv backend/data/historical_1m.csv \
  --model models/rl_training/my_model_ppo \
  --timeframe 5min

# Sweep
python backend/scripts/train_backtest_rl_system.py sweep \
  --csv backend/data/historical_1m.csv
```

## 🚦 Checkpoint Priority

1. **Best checkpoint** (`checkpoints/rl_training/best_models.json`)
   - Models ranked by total return
   - Use for production

2. **Recent checkpoint** (`checkpoints/rl_training/checkpoint_metadata.json`)
   - All trained models with metadata
   - Use for analysis

3. **Sweep checkpoint** (`checkpoints/rl_sweep/sweep_checkpoint.json`)
   - Progress tracker for parameter sweep
   - Auto-resumes on re-run

## 🎁 Example: Resumable Checkpoint System

```python
import json

# Load best models
with open("backend/checkpoints/rl_training/best_models.json") as f:
    best_models = json.load(f)
    for name, info in best_models.items():
        print(f"{name}: Return={info['metrics']['total_return']:.2f}%")
        print(f"  Path: {info['model_path']}")
```

## 🤝 Need Help?

```bash
./rl_train.sh help              # Full documentation
./rl_train.sh list              # Show current status
```

---

**Next Steps:**
1. Upload historical data → `backend/data/historical_1m.csv`
2. Run: `./rl_train.sh train`
3. Backtest: `./rl_train.sh backtest`
4. Monitor: `./rl_train.sh tensorboard`

Happy training! 🚀
