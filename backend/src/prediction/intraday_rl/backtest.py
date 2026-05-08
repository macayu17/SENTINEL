"""Backtesting utilities for intraday RL policies."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Sequence

import numpy as np
import pandas as pd

from .environment import IntradayEnvConfig, IntradayTradingEnv


@dataclass
class SessionBacktestResult:
    session_index: int
    session_start: str
    final_equity: float
    total_pnl: float
    return_pct: float
    max_drawdown_pct: float
    trade_count: int
    win_count: int
    loss_count: int


@dataclass
class BacktestSummary:
    total_sessions: int
    avg_return_pct: float
    total_return_pct: float
    avg_pnl: float
    max_drawdown_pct: float
    win_rate: float
    sharpe_like: float


class ModelProtocol:
    """Small protocol-like wrapper to satisfy static typing without runtime dependency."""

    def predict(self, observation: np.ndarray, deterministic: bool = True):  # pragma: no cover
        raise NotImplementedError


def _calc_max_drawdown(equity_curve: Sequence[float]) -> float:
    peak = -np.inf
    max_dd = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            dd = (peak - equity) / peak
            max_dd = max(max_dd, dd)
    return max_dd


def backtest_model(
    model: ModelProtocol,
    sessions: Sequence[pd.DataFrame],
    env_config: IntradayEnvConfig,
) -> Dict[str, Any]:
    """Run deterministic session-by-session backtest and compute trading metrics."""
    session_results: List[SessionBacktestResult] = []
    all_returns: List[float] = []
    all_drawdowns: List[float] = []

    total_wins = 0
    total_losses = 0

    env = IntradayTradingEnv(sessions=sessions, config=env_config)

    for idx, session in enumerate(sessions):
        obs, info = env.reset(options={"session_index": idx})
        done = False

        equity_curve: List[float] = [float(info["equity"])]
        session_trade_pnls: List[float] = []

        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, _, done, _, step_info = env.step(int(action))
            equity_curve.append(float(step_info["equity"]))

            trade_event = step_info.get("trade_event")
            if trade_event and trade_event.get("side") == "SELL" and "trade_pnl" in trade_event:
                pnl = float(trade_event["trade_pnl"])
                session_trade_pnls.append(pnl)
                if pnl > 0:
                    total_wins += 1
                elif pnl < 0:
                    total_losses += 1

        final_equity = equity_curve[-1]
        total_pnl = final_equity - env_config.initial_cash
        return_pct = (total_pnl / env_config.initial_cash) * 100.0
        dd_pct = _calc_max_drawdown(equity_curve) * 100.0

        session_results.append(
            SessionBacktestResult(
                session_index=idx,
                session_start=str(session.index[0]),
                final_equity=final_equity,
                total_pnl=total_pnl,
                return_pct=return_pct,
                max_drawdown_pct=dd_pct,
                trade_count=len(session_trade_pnls),
                win_count=sum(1 for x in session_trade_pnls if x > 0),
                loss_count=sum(1 for x in session_trade_pnls if x < 0),
            )
        )

        all_returns.append(return_pct)
        all_drawdowns.append(dd_pct)

    total_return_pct = float(np.sum(all_returns))
    avg_return_pct = float(np.mean(all_returns)) if all_returns else 0.0
    avg_pnl = float(np.mean([s.total_pnl for s in session_results])) if session_results else 0.0
    max_drawdown_pct = float(np.max(all_drawdowns)) if all_drawdowns else 0.0

    trade_total = total_wins + total_losses
    win_rate = (total_wins / trade_total) if trade_total > 0 else 0.0

    # Session-level return Sharpe proxy.
    if len(all_returns) > 1:
        mean_ret = float(np.mean(all_returns))
        std_ret = float(np.std(all_returns, ddof=1))
        sharpe_like = (mean_ret / std_ret) * np.sqrt(252.0) if std_ret > 0 else 0.0
    else:
        sharpe_like = 0.0

    summary = BacktestSummary(
        total_sessions=len(session_results),
        avg_return_pct=avg_return_pct,
        total_return_pct=total_return_pct,
        avg_pnl=avg_pnl,
        max_drawdown_pct=max_drawdown_pct,
        win_rate=win_rate,
        sharpe_like=float(sharpe_like),
    )

    return {
        "summary": asdict(summary),
        "session_results": [asdict(row) for row in session_results],
    }
