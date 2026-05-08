# SENTINEL Intraday RL Training Implementation

This branch adds an optional intraday reinforcement-learning workflow on top of
the existing SENTINEL FastAPI backend and Next.js dashboard. The runtime market
simulator remains the version from current `main`; the new files are training,
backtesting, and documentation assets for offline RL experimentation.

## Added Runtime Surface

- `backend/src/prediction/intraday_rl/environment.py`
  - Gymnasium-compatible intraday trading environment.
  - Discrete actions: hold, buy, sell.
  - Tracks cash, position, equity, drawdown, transaction costs, and trailing stop state.

- `backend/src/prediction/intraday_rl/features.py`
  - Loads OHLCV CSV files.
  - Builds SMA, RSI, volume, and return features.
  - Splits minute-bar data into daily sessions and supports simple augmentation.

- `backend/src/prediction/intraday_rl/trainer.py`
  - PPO and DQN training helpers.
  - Optional checkpoint resume support.
  - Shared setup summary for reproducible runs.

- `backend/src/prediction/intraday_rl/backtest.py`
  - Session-by-session deterministic backtesting.
  - Produces return, drawdown, win-rate, and Sharpe-like metrics.

## Added CLI Tools

- `backend/scripts/train_intraday_rl.py`
  - Focused PPO/DQN training entrypoint.

- `backend/scripts/backtest_intraday_rl.py`
  - Loads a trained model and evaluates it on 1m, 5m, or 15m bars.

- `backend/scripts/train_backtest_rl_system.py`
  - Higher-level training, backtesting, checkpoint, and sweep orchestrator.

- `backend/scripts/prepare_training_data.py`
  - Converts available stock CSV files under `backend/data/` into `historical_1m.csv`.

- `rl_train.sh`
  - Convenience wrapper for train, backtest, sweep, list, tensorboard, and cleanup flows.

- `verify_rl_setup.sh`
  - Checks local shell/Python setup and required RL packages.

## Dependencies

The base backend dependencies stay in `backend/requirements.txt`.
RL-only packages are isolated in `backend/requirements-rl.txt`:

```text
pandas
stable-baselines3[extra]==2.7.1
tensorboard
```

Install both sets when using the training system:

```bash
pip install -r backend/requirements.txt
pip install -r backend/requirements-rl.txt
```

## Minimal Workflow

```bash
# 1. Verify setup
./verify_rl_setup.sh

# 2. Put OHLCV data at:
# backend/data/historical_1m.csv

# 3. Train a quick PPO model
./rl_train.sh train test_model ppo 50000

# 4. Backtest it
./rl_train.sh backtest test_model
```

The training commands create generated artifacts under ignored directories:

- `backend/models/rl_training/`
- `backend/checkpoints/`
- `backend/results/`
- `backend/tensorboard_logs/`

These outputs are intentionally not committed.

## Verification Performed

The resolved branch was checked with:

```bash
python -m py_compile backend/RL_CONFIG_TEMPLATES.py backend/scripts/backtest_intraday_rl.py backend/scripts/prepare_training_data.py backend/scripts/train_backtest_rl_system.py backend/scripts/train_intraday_rl.py backend/src/prediction/intraday_rl/__init__.py backend/src/prediction/intraday_rl/backtest.py backend/src/prediction/intraday_rl/environment.py backend/src/prediction/intraday_rl/features.py backend/src/prediction/intraday_rl/trainer.py
python -m pytest -q backend/tests
npm run lint
npm run build
docker compose config
docker compose build
```
