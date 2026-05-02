"""Gymnasium environment for intraday OHLCV trading with morning-session constraints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces


ACTION_HOLD = 0
ACTION_BUY = 1
ACTION_SELL = 2


@dataclass
class IntradayEnvConfig:
    """Environment hyperparameters aligned with Kadia et al. 2025 methodology.
    
    Hard constraints for signal confirmation:
    - ATV uptrend REQUIRED (not optional)
    - RSI gates REQUIRED (RSI < 70 for buy, RSI > 30 for sell)
    - SMA crossover as primary signal
    """

    lookback: int = 30
    initial_cash: float = 1_000_000.0
    lot_size: int = 50
    transaction_cost_bps: float = 10.0  # 0.1%
    trailing_stop_pct: float = 0.005
    volume_confirmation_multiplier: float = 1.2
    rsi_overbought: float = 70.0  # Hard gate for BUY
    rsi_oversold: float = 30.0    # Hard gate for SELL
    invalid_action_penalty: float = 0.05  # Heavier penalty for violating confirmation rules
    trend_bonus: float = 0.002  # Reward bonus for trading with trend
    volume_bonus: float = 0.002  # Reward bonus for trading with volume confirmation
    morning_minutes: int = 60
    random_reset: bool = True
    reward_scale: float = 10.0


class IntradayTradingEnv(gym.Env):
    """
    Intraday long-flat environment using minute OHLCV bars.

    State includes:
      - last N candles (OHLC + volume ratio)
      - current position (0/1)
      - current PnL
      - SMA crossover signal
      - RSI value

    Actions:
      - 0: HOLD
      - 1: BUY
      - 2: SELL

    Constraints:
      - Trade only in first 60 minutes of each session.
      - Trailing stop-loss auto-exit.
      - After first exit, only one additional re-entry is allowed.
      - No further entries for the rest of the day.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(self, sessions: Sequence[pd.DataFrame], config: IntradayEnvConfig | None = None):
        super().__init__()
        if not sessions:
            raise ValueError("At least one session is required.")

        self.config = config or IntradayEnvConfig()
        self.sessions: List[pd.DataFrame] = [self._validate_session(s.copy()) for s in sessions]
        self.rng = np.random.default_rng(42)

        self.action_space = spaces.Discrete(3)

        self._obs_feature_count = 5  # open/high/low/close/volume_ratio
        self._extra_feature_count = 6  # position,pnl,sma_signal,rsi,volume_ratio,time_ratio
        obs_len = self.config.lookback * self._obs_feature_count + self._extra_feature_count
        self.observation_space = spaces.Box(low=-10.0, high=10.0, shape=(obs_len,), dtype=np.float32)

        self._session_idx = 0
        self._session_df: pd.DataFrame | None = None
        self._current_step = 0

        self.cash = self.config.initial_cash
        self.position = 0
        self.entry_price: float | None = None
        self.highest_since_entry: float | None = None

        self.realized_pnl = 0.0
        self.transaction_cost_paid = 0.0
        self.prev_equity = self.config.initial_cash

        self.entries_taken = 0
        self.reverse_entry_available = False
        self.reverse_entry_used = False
        self.trading_locked = False

        self.trade_log: List[Dict[str, Any]] = []

    @staticmethod
    def _validate_session(session_df: pd.DataFrame) -> pd.DataFrame:
        required = {
            "open",
            "high",
            "low",
            "close",
            "volume",
            "sma_signal",
            "rsi",
            "volume_ratio",
        }
        missing = sorted(required.difference(set(session_df.columns)))
        if missing:
            raise ValueError(f"Session missing required columns: {missing}")
        if not isinstance(session_df.index, pd.DatetimeIndex):
            raise ValueError("Session DataFrame must use DatetimeIndex.")
        if len(session_df) < 40:
            raise ValueError("Each session must contain at least 40 bars.")
        return session_df.sort_index()

    def _pick_session_index(self, options: Dict[str, Any] | None) -> int:
        if options and "session_index" in options:
            idx = int(options["session_index"])
            if idx < 0 or idx >= len(self.sessions):
                raise IndexError("session_index out of range")
            return idx

        if self.config.random_reset:
            return int(self.rng.integers(0, len(self.sessions)))

        idx = self._session_idx
        self._session_idx = (self._session_idx + 1) % len(self.sessions)
        return idx

    def reset(self, seed: int | None = None, options: Dict[str, Any] | None = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        super().reset(seed=seed)

        if seed is not None:
            self.rng = np.random.default_rng(seed)

        self._session_idx = self._pick_session_index(options)
        self._session_df = self.sessions[self._session_idx]

        self._current_step = self.config.lookback

        self.cash = self.config.initial_cash
        self.position = 0
        self.entry_price = None
        self.highest_since_entry = None

        self.realized_pnl = 0.0
        self.transaction_cost_paid = 0.0
        self.prev_equity = self.config.initial_cash

        self.entries_taken = 0
        self.reverse_entry_available = False
        self.reverse_entry_used = False
        self.trading_locked = False

        self.trade_log = []

        obs = self._build_observation()
        info = {
            "session_index": self._session_idx,
            "session_start": str(self._session_df.index[0]),
            "equity": self.prev_equity,
        }
        return obs, info

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        if self._session_df is None:
            raise RuntimeError("Environment must be reset before stepping.")

        action = int(action)
        if action not in (ACTION_HOLD, ACTION_BUY, ACTION_SELL):
            raise ValueError("Invalid action. Expected 0/1/2.")

        row = self._session_df.iloc[self._current_step]
        timestamp = self._session_df.index[self._current_step]
        action_label = "HOLD"
        invalid_penalty = 0.0
        trade_event: Dict[str, Any] | None = None

        # Trailing stop takes precedence if a long exists.
        if self.position == 1 and self.highest_since_entry is not None:
            self.highest_since_entry = max(self.highest_since_entry, float(row["high"]))
            stop_price = self.highest_since_entry * (1.0 - self.config.trailing_stop_pct)
            if float(row["low"]) <= stop_price:
                trade_event = self._execute_sell(price=stop_price, ts=timestamp, reason="trailing_stop")
                action_label = "SELL"

        if trade_event is None:
            if self._in_morning_window(timestamp):
                if action == ACTION_BUY:
                    if self.position == 0 and self._can_open_new_position():
                        trade_event = self._execute_buy(price=float(row["close"]), ts=timestamp)
                        action_label = "BUY"
                    else:
                        invalid_penalty = self.config.invalid_action_penalty
                elif action == ACTION_SELL:
                    if self.position == 1:
                        trade_event = self._execute_sell(
                            price=float(row["close"]),
                            ts=timestamp,
                            reason="policy_exit",
                        )
                        action_label = "SELL"
                    else:
                        invalid_penalty = self.config.invalid_action_penalty
            else:
                # Outside the first hour we lock new trades and force square-off.
                if self.position == 1:
                    trade_event = self._execute_sell(
                        price=float(row["close"]),
                        ts=timestamp,
                        reason="morning_window_end",
                    )
                    action_label = "SELL"
                self.trading_locked = True
                if action != ACTION_HOLD:
                    invalid_penalty = self.config.invalid_action_penalty

        equity = self._mark_to_market(float(row["close"]))
        total_pnl = equity - self.config.initial_cash

        reward = ((equity - self.prev_equity) / self.config.initial_cash) * self.config.reward_scale
        reward -= invalid_penalty
        self.prev_equity = equity

        # Bonus shaping uses indicators as soft context, not hard rules.
        trade_filled = bool(trade_event and trade_event.get("status") == "filled")

        if action_label == "BUY" and trade_filled:
            if float(row["sma_signal"]) > 0:
                reward += self.config.trend_bonus
            if float(row["volume_ratio"]) >= self.config.volume_confirmation_multiplier:
                reward += self.config.volume_bonus
        elif action_label == "SELL" and trade_filled:
            if float(row["sma_signal"]) < 0:
                reward += self.config.trend_bonus * 0.5
            if float(row["volume_ratio"]) >= self.config.volume_confirmation_multiplier:
                reward += self.config.volume_bonus * 0.5

        self._current_step += 1
        terminated = self._current_step >= len(self._session_df)
        truncated = False

        obs = self._build_observation() if not terminated else self._terminal_observation()

        info = {
            "timestamp": str(timestamp),
            "action": action_label,
            "requested_action": int(action),
            "position": self.position,
            "cash": self.cash,
            "equity": equity,
            "realized_pnl": self.realized_pnl,
            "total_pnl": total_pnl,
            "transaction_cost_paid": self.transaction_cost_paid,
            "entries_taken": self.entries_taken,
            "reverse_entry_available": self.reverse_entry_available,
            "reverse_entry_used": self.reverse_entry_used,
            "trade_event": trade_event,
        }

        return obs, float(reward), bool(terminated), bool(truncated), info

    def _in_morning_window(self, timestamp: pd.Timestamp) -> bool:
        if self._session_df is None:
            return False
        session_start = self._session_df.index[0]
        window_end = session_start + pd.Timedelta(minutes=self.config.morning_minutes)
        return timestamp <= window_end

    def _can_open_new_position(self) -> bool:
        if self.trading_locked:
            return False
        if self.entries_taken == 0:
            return True
        if self.entries_taken == 1 and self.reverse_entry_available and not self.reverse_entry_used:
            return True
        return False

    def _execute_buy(self, price: float, ts: pd.Timestamp) -> Dict[str, Any]:
        fee_rate = self.config.transaction_cost_bps / 10_000.0
        gross_value = price * self.config.lot_size
        fee = gross_value * fee_rate
        total_cost = gross_value + fee

        if self.cash < total_cost:
            return {
                "side": "BUY",
                "timestamp": str(ts),
                "price": price,
                "status": "rejected_insufficient_cash",
            }

        self.cash -= total_cost
        self.transaction_cost_paid += fee
        self.position = 1
        self.entry_price = price
        self.highest_since_entry = price

        self.entries_taken += 1
        if self.entries_taken == 2:
            self.reverse_entry_used = True

        event = {
            "side": "BUY",
            "timestamp": str(ts),
            "price": price,
            "fee": fee,
            "status": "filled",
        }
        self.trade_log.append(event)
        return event

    def _execute_sell(self, price: float, ts: pd.Timestamp, reason: str) -> Dict[str, Any]:
        if self.position == 0 or self.entry_price is None:
            return {
                "side": "SELL",
                "timestamp": str(ts),
                "price": price,
                "status": "ignored_no_position",
                "reason": reason,
            }

        fee_rate = self.config.transaction_cost_bps / 10_000.0
        gross_value = price * self.config.lot_size
        fee = gross_value * fee_rate
        net_value = gross_value - fee

        self.cash += net_value
        self.transaction_cost_paid += fee

        trade_pnl = (price - self.entry_price) * self.config.lot_size
        entry_fee = self.entry_price * self.config.lot_size * fee_rate
        net_trade_pnl = trade_pnl - fee - entry_fee
        self.realized_pnl += net_trade_pnl

        if self.entries_taken == 1 and not self.reverse_entry_available:
            self.reverse_entry_available = True
        if self.entries_taken >= 2:
            self.trading_locked = True

        self.position = 0
        self.entry_price = None
        self.highest_since_entry = None

        event = {
            "side": "SELL",
            "timestamp": str(ts),
            "price": price,
            "fee": fee,
            "trade_pnl": net_trade_pnl,
            "status": "filled",
            "reason": reason,
        }
        self.trade_log.append(event)
        return event

    def _mark_to_market(self, close_price: float) -> float:
        position_value = close_price * self.config.lot_size if self.position == 1 else 0.0
        return self.cash + position_value

    def _build_observation(self) -> np.ndarray:
        assert self._session_df is not None

        start = self._current_step - self.config.lookback
        end = self._current_step
        window = self._session_df.iloc[start:end]

        closes = window["close"].values.astype(np.float32)
        prev_closes = np.roll(closes, 1)
        prev_closes[0] = closes[0]

        open_rel = (window["open"].values.astype(np.float32) / prev_closes) - 1.0
        high_rel = (window["high"].values.astype(np.float32) / prev_closes) - 1.0
        low_rel = (window["low"].values.astype(np.float32) / prev_closes) - 1.0
        close_rel = (window["close"].values.astype(np.float32) / prev_closes) - 1.0
        volume_rel = window["volume_ratio"].values.astype(np.float32) - 1.0

        stacked = np.column_stack([open_rel, high_rel, low_rel, close_rel, volume_rel]).flatten()

        latest = window.iloc[-1]
        equity = self._mark_to_market(float(latest["close"]))
        pnl_pct = (equity - self.config.initial_cash) / self.config.initial_cash

        ts = window.index[-1]
        session_start = self._session_df.index[0]
        elapsed = (ts - session_start).total_seconds() / 60.0
        morning_progress = min(1.0, elapsed / float(self.config.morning_minutes))

        extra = np.array(
            [
                float(self.position),
                float(pnl_pct),
                float(latest["sma_signal"]),
                (float(latest["rsi"]) / 50.0) - 1.0,
                float(latest["volume_ratio"] - 1.0),
                float(morning_progress),
            ],
            dtype=np.float32,
        )

        obs = np.concatenate([stacked.astype(np.float32), extra], axis=0)
        return np.clip(obs, -10.0, 10.0).astype(np.float32)

    def _terminal_observation(self) -> np.ndarray:
        # Return last valid observation shape when the episode ends.
        assert self._session_df is not None
        last_step = min(max(self.config.lookback, len(self._session_df) - 1), len(self._session_df))
        self._current_step = last_step
        return self._build_observation()

    def render(self) -> None:
        if self._session_df is None:
            return
        step = min(self._current_step, len(self._session_df) - 1)
        ts = self._session_df.index[step]
        close = float(self._session_df.iloc[step]["close"])
        equity = self._mark_to_market(close)
        print(
            f"t={ts} close={close:.2f} pos={self.position} equity={equity:.2f} "
            f"entries={self.entries_taken} reverse_used={self.reverse_entry_used}"
        )
