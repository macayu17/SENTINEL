
# 🎯 Sentinel RL Training System - Complete Documentation

## 📍 You Are Here
This directory contains a **production-grade reinforcement learning training system** for intraday trading with:
- ✅ Model training (PPO/DQN)
- ✅ Automatic checkpointing
- ✅ Resumable parameter sweeps
- ✅ Multi-timeframe backtesting
- ✅ Detailed metrics & comparison
- ✅ Tensorboard monitoring

## 🚀 Getting Started (Choose Your Path)

### ⚡ I Just Want to Train (5 minutes)
1. Read: [RL_QUICK_START.md](RL_QUICK_START.md)
2. Run: `./rl_train.sh train test ppo 50000`
3. Backtest: `./rl_train.sh backtest test`

### 📚 I Want to Understand Everything (30 minutes)
1. Read: [SETUP_RL_TRAINING.md](SETUP_RL_TRAINING.md) — Complete workflow
2. Read: [RL_QUICK_START.md](RL_QUICK_START.md) — Command reference
3. Run: `./verify_rl_setup.sh` — Verify installation
4. Explore: `./rl_train.sh help` — Command help

### 🔍 I Need Complete Reference (60 minutes)
1. Read: [RL_SYSTEM_SUMMARY.md](RL_SYSTEM_SUMMARY.md) — System overview
2. Read: [RL_TRAINING_GUIDE.md](RL_TRAINING_GUIDE.md) — Full manual
3. Read: [backend/RL_CONFIG_TEMPLATES.py](backend/RL_CONFIG_TEMPLATES.py) — Configuration examples

### 🐛 I'm Troubleshooting
1. Check: [RL_TRAINING_GUIDE.md#troubleshooting](RL_TRAINING_GUIDE.md) — Common issues
2. Run: `./verify_rl_setup.sh` — Verify setup
3. Check: `./rl_train.sh list` — View current status

---

## 📂 File Structure

```
Sentinel/ (You are here)
│
├─ Documentation (Read These First)
│  ├── README.md                          ← This file
│  ├── RL_QUICK_START.md                  ← Commands cheat sheet
│  ├── SETUP_RL_TRAINING.md              ← Complete setup guide
│  ├── RL_TRAINING_GUIDE.md              ← Full reference manual
│  └── RL_SYSTEM_SUMMARY.md              ← System architecture
│
├─ Executable Scripts
│  ├── rl_train.sh                        ← Main wrapper (use this!)
│  └── verify_rl_setup.sh                 ← Verify installation
│
├─ backend/
│  ├── scripts/
│  │  └── train_backtest_rl_system.py    ← Core training system (600+ lines)
│  │
│  ├── RL_CONFIG_TEMPLATES.py            ← Configuration examples
│  │
│  ├── data/
│  │  └── historical_1m.csv              ← 📤 Upload your data here
│  │
│  ├── models/rl_training/
│  │  └── [trained_models]               ← Saved trained models
│  │
│  ├── checkpoints/rl_training/
│  │  ├── checkpoint_metadata.json       ← Model metadata
│  │  └── best_models.json               ← Best models
│  │
│  ├── results/rl_training/
│  │  └── [backtest_results]             ← Backtest metrics
│  │
│  └── tensorboard_logs/
│     ├── intraday_ppo/                  ← PPO training curves
│     └── intraday_dqn/                  ← DQN training curves
│
└── Output Directories (Auto-Created)
   ├── models/rl_sweep/                  ← Sweep results
   ├── checkpoints/rl_sweep/             ← Sweep progress
   └── results/rl_sweep/                 ← Sweep metrics
```

---

## 📖 Quick Reference

### Most Common Commands

```bash
# 1️⃣  Upload your data (do this first!)
cp /path/to/your/data.csv backend/data/historical_1m.csv

# 2️⃣  Train a model
./rl_train.sh train model_name ppo 250000

# 3️⃣  Backtest it
./rl_train.sh backtest model_name

# 4️⃣  Find best hyperparameters
./rl_train.sh sweep

# 5️⃣  View all models and results
./rl_train.sh list

# 6️⃣  Monitor training live
./rl_train.sh tensorboard
```

### All Commands

```bash
./rl_train.sh train [name] [algo] [timesteps] [lr] [arch]
./rl_train.sh backtest <name> [algo] [timeframe]
./rl_train.sh sweep [--force-fresh]
./rl_train.sh list
./rl_train.sh tensorboard [port]
./rl_train.sh cleanup
./rl_train.sh help
```

See [RL_QUICK_START.md](RL_QUICK_START.md) for detailed examples.

---

## 🎯 Typical Workflow

### Day 1: Testing
```bash
# Quick test to verify everything works
./rl_train.sh train quick ppo 50000
./rl_train.sh backtest quick

# Result: "It works! Now let's find the best parameters"
```

### Day 2: Optimization
```bash
# Find best hyperparameters (2-3 hours)
./rl_train.sh sweep

# Result: "lr=3e-4, arch=256,256 is best"
```

### Day 3: Production Training
```bash
# Full training with best parameters (1-2 hours)
./rl_train.sh train production ppo 500000 3e-4 256,256

# Multi-timeframe testing
./rl_train.sh backtest production ppo 1min
./rl_train.sh backtest production ppo 5min    # Deploy at 5min
./rl_train.sh backtest production ppo 15min

# Monitor
./rl_train.sh tensorboard
```

Full workflow: [SETUP_RL_TRAINING.md](SETUP_RL_TRAINING.md)

---

## 🔑 Key Features

### 1. **Automatic Checkpointing**
- Save models after training
- Track best models by performance
- Resume interrupted training

### 2. **Parameter Sweep (Resumable)**
- Test multiple hyperparameters automatically
- Safe to interrupt (Ctrl+C) — resumes automatically
- Ranked results by performance metric

### 3. **Detailed Backtesting**
```json
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

### 4. **Multi-Timeframe Testing**
- Train at 1-minute bars (highest frequency)
- Test/deploy at 5min or 15min bars (smoother)
- Use same model at different speeds

### 5. **Live Monitoring**
```bash
./rl_train.sh tensorboard
# Open http://localhost:6006 in browser
```

---

## 📊 Checkpoint System (Key Feature!)

### Automatic Resume After Interruption

```bash
# Start 2-hour sweep
./rl_train.sh sweep
# [After 1 hour, machine crashes]

# Re-run — automatically resumes!
./rl_train.sh sweep
# ✅ Picks up from saved checkpoint
# ✅ Skips already-tested combinations
```

This is saved in: `backend/checkpoints/rl_sweep/sweep_checkpoint.json`

---

## 💻 System Requirements

✅ **Python 3.8+** (verified: 3.13.2)

🔧 **Required Packages:**
```bash
pip install stable_baselines3 gymnasium pandas numpy
pip install tensorboard  # Optional, for monitoring
```

💾 **Disk Space:**
- Models: ~50MB each
- Tensorboard logs: ~100MB per training run
- Data: Your historical data size

---

## 🎓 Learning Resources

| Resource | Purpose | Time |
|----------|---------|------|
| [RL_QUICK_START.md](RL_QUICK_START.md) | Commands & examples | 10 min |
| [SETUP_RL_TRAINING.md](SETUP_RL_TRAINING.md) | Complete workflow | 30 min |
| [RL_TRAINING_GUIDE.md](RL_TRAINING_GUIDE.md) | Full reference manual | 60 min |
| [RL_SYSTEM_SUMMARY.md](RL_SYSTEM_SUMMARY.md) | Architecture overview | 20 min |
| [backend/RL_CONFIG_TEMPLATES.py](backend/RL_CONFIG_TEMPLATES.py) | Configuration examples | 15 min |

---

## 🚦 Expected Performance

**Good Model (Profitable):**
- Total return: > 5%
- Win rate: > 55%
- Sharpe: > 1.0
- Max drawdown: < -10%

**Excellent Model (Highly Profitable):**
- Total return: > 15%
- Win rate: > 65%
- Sharpe: > 1.5
- Max drawdown: < -5%

See [RL_TRAINING_GUIDE.md#performance-expectations](RL_TRAINING_GUIDE.md) for more details.

---

## 🔧 Troubleshooting

### "No historical_1m.csv found"
```bash
cp /path/to/your/data.csv backend/data/historical_1m.csv
```

### "Missing packages"
```bash
pip install stable_baselines3 gymnasium pandas numpy
```

### "Sweep interrupted"
```bash
# Just re-run — it auto-resumes!
./rl_train.sh sweep
```

### "Poor performance"
```bash
# Run sweep to find best hyperparameters
./rl_train.sh sweep

# Then train with best params found
./rl_train.sh train model ppo 500000 3e-4 256,256
```

See [RL_TRAINING_GUIDE.md#troubleshooting](RL_TRAINING_GUIDE.md#troubleshooting) for more.

---

## 📈 Next Steps

1. **Verify Setup**
   ```bash
   ./verify_rl_setup.sh
   ```

2. **Prepare Data**
   ```bash
   cp your_data.csv backend/data/historical_1m.csv
   ```

3. **Quick Test**
   ```bash
   ./rl_train.sh train test ppo 50000
   ./rl_train.sh backtest test
   ```

4. **Explore Documentation**
   - Start with: [RL_QUICK_START.md](RL_QUICK_START.md)
   - Deep dive: [RL_TRAINING_GUIDE.md](RL_TRAINING_GUIDE.md)

5. **Run Full Workflow**
   ```bash
   ./rl_train.sh sweep
   ./rl_train.sh train production ppo 500000 3e-4 256,256
   ./rl_train.sh backtest production
   ```

---

## 📞 Help & Support

```bash
# Get help
./rl_train.sh help

# View quick reference
cat RL_QUICK_START.md

# Read full manual
cat RL_TRAINING_GUIDE.md

# Check setup
./verify_rl_setup.sh

# See current models
./rl_train.sh list
```

---

## 📝 File Summary

| File | Purpose | Lines |
|------|---------|-------|
| `train_backtest_rl_system.py` | Core training system | 600+ |
| `rl_train.sh` | CLI wrapper | 450+ |
| `RL_TRAINING_GUIDE.md` | Comprehensive reference | 400+ |
| `RL_QUICK_START.md` | Commands cheat sheet | 300+ |
| `SETUP_RL_TRAINING.md` | Setup guide | 350+ |
| `RL_SYSTEM_SUMMARY.md` | System overview | 400+ |
| `RL_CONFIG_TEMPLATES.py` | Config examples | 350+ |
| `verify_rl_setup.sh` | Setup verification | 100+ |

**Total: 2,950+ lines of production-ready code and documentation**

---

## ✅ Verification Checklist

Run this to verify everything is set up:
```bash
./verify_rl_setup.sh
```

Expected output:
```
✓ Checking Python3... OK
✓ Checking main training script... Found
✓ Checking bash wrapper... Found (executable)
✓ Checking documentation... All docs found
✓ Checking Python syntax... Valid
✓ Checking/creating directories... OK
✓ Setup verification complete!
```

---

## 🎯 Get Started Now!

### Option 1: I'm in a hurry (5 minutes)
```bash
./rl_train.sh train test ppo 50000
./rl_train.sh backtest test
```

### Option 2: I want to understand (30 minutes)
```bash
cat RL_QUICK_START.md              # 10 min
./verify_rl_setup.sh               # 5 min
./rl_train.sh train test ppo 50000 # 10 min
./rl_train.sh backtest test        # 5 min
```

### Option 3: I want complete knowledge (90 minutes)
```bash
cat RL_SYSTEM_SUMMARY.md           # 15 min
cat SETUP_RL_TRAINING.md           # 30 min
cat RL_TRAINING_GUIDE.md           # 30 min
./rl_train.sh train test ppo 50000 # 10 min
./rl_train.sh sweep                # Interactive exploration
```

---

**Happy Training! 🚀📈**

*For the latest updates and additional resources, check [RL_TRAINING_GUIDE.md](RL_TRAINING_GUIDE.md)*
