"""Dashboard payload contract tests for websocket update compatibility."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from src.api import main


class _FakeAgent:
    def __init__(self, agent_id: str, agent_type: str) -> None:
        self.agent_id = agent_id
        self._agent_type = agent_type

    def get_metrics(self, current_price: float) -> Dict[str, Any]:
        return {
            "total_pnl": 10.0,
            "realized_pnl": 6.0,
            "unrealized_pnl": 4.0,
            "return_pct": 0.02,
            "sharpe_ratio": 1.2,
            "agent_type": self._agent_type,
            "position": 3,
            "num_trades": 5,
        }


class _FakeSimulator:
    def __init__(self) -> None:
        self.running = False
        self.current_time = 0.0
        self.duration_seconds = 1.0
        self.current_price = 100.0
        self.agents = [_FakeAgent("RL_1", "RL_MM"), _FakeAgent("MM_1", "MM")]

    def step(self) -> Dict[str, Any]:
        self.current_time = 1.0
        self.current_price = 100.05
        return {
            "current_time": self.current_time,
            "current_price": self.current_price,
            "mid_price": 100.05,
            "best_bid": 100.0,
            "best_ask": 100.1,
            "spread": 0.1,
            "total_depth": 100,
            "order_book_imbalance": 0.05,
            "order_book_levels": {
                "bids": [{"price": 100.0, "size": 55}],
                "asks": [{"price": 100.1, "size": 45}],
            },
            "volatility": 0.01,
            "time_to_close": 0.0,
            "step": 1,
            "recent_signed_volume": 1.0,
            "recent_price_change": 0.001,
        }

    def get_recent_activity(self, limit: int = 20) -> Dict[str, Any]:
        return {
            "orders": [
                {
                    "ts": 1.0,
                    "order_id": "o-1",
                    "agent_id": "MM_1",
                    "side": "BUY",
                    "order_type": "LIMIT",
                    "price": 100.0,
                    "quantity": 5,
                    "status": "Submitted",
                }
            ],
            "trades": [
                {
                    "ts": 1.0,
                    "trade_id": "t-1",
                    "price": 100.05,
                    "quantity": 3,
                    "buyer_agent_id": "MM_1",
                    "seller_agent_id": "HFT_1",
                    "aggressor_side": "BUY",
                }
            ],
            "events": [
                {
                    "ts": 1.0,
                    "type": "Kernel",
                    "severity": "info",
                    "message": "tick",
                    "metadata": {},
                }
            ],
            "agent_actions": {"MM_1": "quote_refresh"},
        }


class _CaptureManager:
    def __init__(self) -> None:
        self.client_count = 1
        self.updates: List[Dict[str, Any]] = []

    async def broadcast(self, update: Dict[str, Any]) -> None:
        self.updates.append(update)


def test_simulation_websocket_payload_dashboard_v1_contract(monkeypatch) -> None:
    fake_manager = _CaptureManager()
    fake_sim = _FakeSimulator()

    monkeypatch.setattr(main, "manager", fake_manager)
    monkeypatch.setattr(main, "simulator", fake_sim)

    async def _fast_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(main.asyncio, "sleep", _fast_sleep)

    asyncio.run(main._run_simulation_loop())

    assert fake_manager.updates, "Expected at least one websocket broadcast update"
    payload = fake_manager.updates[-1]

    assert payload["data_contract_version"] == "dashboard.v1"
    assert payload["type"] == "market_update"
    assert payload["signal"]["signal"] in {"BUY", "SELL", "HOLD"}
    assert payload["mode"] in {"SIMULATION", "LIVE_SHADOW"}
    assert "rl_status" in payload
    assert "phase_status" in payload
    assert "live_feed" in payload

    frontend_required = {
        "timestamp",
        "price",
        "spread",
        "depth",
        "order_book",
        "liquidity_prediction",
        "agent_metrics",
        "step",
        "volatility",
        "mode",
        "signal",
        "live_feed",
    }
    missing = frontend_required.difference(payload.keys())
    assert not missing, f"Missing frontend-required payload keys: {sorted(missing)}"

    live_feed = payload["live_feed"]
    assert "provider" in live_feed
    assert "transport" in live_feed
    assert "stale" in live_feed
    assert "latency_ms" in live_feed
