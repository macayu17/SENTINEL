# Combined Intraday RL System (Indicator + DARL)

This document describes the implementation added under `src/prediction/intraday_rl/`.
It combines:

1. Indicator-driven feature context (SMA crossover, RSI, ATV/volume confirmation)
2. Data-augmentation RL workflow (train on dense 1-minute bars, deploy on 5-minute/15-minute bars)

## 1) Architecture Diagram (Text)

```
Minute OHLCV (NSE Futures)
        |
        v
Feature Layer
- SMA short/long
- SMA signal (sign of crossover)
- RSI
- ATV and volume_ratio
        |
        v
Data Strategy Layer
- Split into daily sessions
- Augment minute sessions (noise-based synthetic sessions)
        |
        v
RL Environment (IntradayTradingEnv)
State:
- Last N candles (OHLC + volume_ratio)
- Position (0/1)
- Current PnL
- SMA signal
- RSI
Actions:
- HOLD / BUY / SELL
Execution Constraints:
- First 60 minutes only
- Trailing stop
- One reverse re-entry max after first exit
Reward:
- Delta equity (net of costs)
- Trend alignment bonus (SMA)
- Volume confirmation bonus (ATV ratio)
        |
        v
Policy Model
- Primary: PPO (MlpPolicy)
- Optional baseline: DQN
        |
        v
Deployment/Backtest
- Same policy on 5m/15m data (resampled)
- Session-wise metrics: return, drawdown, win rate, sharpe-like
```

## 2) Step-by-step Pipeline

1. Load minute OHLCV CSV (`timestamp, open, high, low, close, volume`).
2. Build indicators with `build_intraday_features(...)`.
3. Split into daily episodes with `split_sessions(...)`.
4. Apply augmentation using `MinuteDataAugmenter` (DARL-style robustness).
5. Train PPO in `IntradayTradingEnv`:
   - trading cost = 0.1%
   - trading window = first 60 minutes
   - trailing stop active when in position
   - one additional re-entry allowed after first exit
6. Save model.
7. Backtest on 1m and also 5m/15m using `resample_ohlcv(...)` + `backtest_model(...)`.

## 3) Python-like Implementation Entry Points

Train:

```bash
cd backend
python scripts/train_intraday_rl.py \
  --csv /path/to/nse_minute_ohlcv.csv \
  --output-model models/intraday_ppo \
  --total-timesteps 250000 \
  --lookback 30 \
  --copies-per-session 1
```

Backtest on 5-minute bars:

```bash
cd backend
python scripts/backtest_intraday_rl.py \
  --csv /path/to/nse_minute_ohlcv.csv \
  --model models/intraday_ppo \
  --algo ppo \
  --timeframe 5min
```

Backtest on 15-minute bars:

```bash
cd backend
python scripts/backtest_intraday_rl.py \
  --csv /path/to/nse_minute_ohlcv.csv \
  --model models/intraday_ppo \
  --algo ppo \
  --timeframe 15min
```

## 4) Reward Function Design (Implemented)

At each step:

- Base reward:
  - `reward_base = ((equity_t - equity_{t-1}) / initial_cash) * reward_scale`
  - equity already includes transaction costs and mark-to-market effect.
- Cost:
  - buy/sell fee at 0.1% (`transaction_cost_bps = 10`)
- Penalty:
  - invalid action penalty for illegal trades (outside window, selling with no position, etc.)
- Bonus:
  - trend bonus when executed BUY aligns with positive SMA signal
  - trend bonus (reduced) when executed SELL aligns with negative SMA signal
  - volume bonus when `volume_ratio >= volume_confirmation_multiplier`

Final reward:

```
reward = reward_base - invalid_penalty + trend_bonus + volume_bonus
```

## 5) Why 1-minute Train -> 5m/15m Deploy

- 1-minute bars expose more state transitions, improving sample efficiency for PPO.
- The model learns early-session micro-structure transitions (opening impulse, pullback, continuation).
- Deployment on 5m/15m reduces execution noise and over-trading while preserving learned directional priors.
- Indicators are recomputed after resampling, so SMA/RSI/ATV semantics remain consistent.

## 6) Backtesting Protocol

1. Keep training and backtest dates disjoint.
2. Train on minute sessions.
3. Evaluate on:
   - minute sessions (in-sample behavior check)
   - 5m/15m transformed sessions (deployment proxy)
4. Report:
   - average return/session
   - total return
   - max drawdown
   - win rate (sell trades with positive net PnL)
   - sharpe-like ratio from session returns
5. Stress scenarios:
   - high-gap days
   - low-liquidity mornings
   - trend reversal mornings

## 7) Common Pitfalls and Improvements

Pitfalls:
- Data leakage from indicator windows crossing train/test boundaries.
- Non-stationary regime shifts (event days, policy announcements).
- Ignoring slippage in fast opening minutes.
- Overfitting to one symbol/contract month.

Improvements:
- Add explicit slippage model (spread + impact).
- Add walk-forward retraining schedule by month.
- Extend state with opening range features and gap context.
- Move from long/flat to long/flat/short if strategy mandate allows.
- Add SAC only if action space is redesigned to continuous sizing/execution controls.

## 8) Files Added

- `src/prediction/intraday_rl/features.py`
- `src/prediction/intraday_rl/environment.py`
- `src/prediction/intraday_rl/trainer.py`
- `src/prediction/intraday_rl/backtest.py`
- `src/prediction/intraday_rl/__init__.py`
- `scripts/train_intraday_rl.py`
- `scripts/backtest_intraday_rl.py`
